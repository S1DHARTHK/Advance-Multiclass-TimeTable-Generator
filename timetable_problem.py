"""
timetable_problem.py
--------------------
The scheduling problem, built from a plain dataset dictionary.

This module is the only place that knows the *shape* of the input data.
It turns a dataset dict into flat, index-based structures the GA can work
on quickly, and it never imports the data generator, Laravel, FastAPI or a
database. Anything that can hand over a dict in the documented shape works:

    problem = TimetableProblem.from_dataset(json.load(open("data.json")))
    problem = TimetableProblem.from_dataset(requests.get(url).json())
    problem = TimetableProblem.from_dataset(build_dataset(CONFIG))

Core ideas
----------
Unit    One thing that has to be placed in the week: either a class lesson
        (one teacher, one class) or a language band (see below). A unit
        needs `periods` distinct slots.

Band    Second language is taught to several groups at the same time: while
        the language teachers each take their own group, every class that
        feeds those groups is busy. Groups that share a class must therefore
        run in the same slots. Groups are linked into bands accordingly
        (connected components over shared classes), and a band is scheduled
        as one unit - which is what makes language-group scheduling valid
        by construction rather than by luck.

Slots are indexed 0..N-1 in day-major order, so slot // periods_per_day is
the day and slot % periods_per_day is the period.
"""

from collections import defaultdict


class Unit:
    """One schedulable item: a class lesson or a language band."""

    __slots__ = (
        "index", "unit_id", "kind", "label", "periods",
        "class_indexes", "teacher_indexes", "subject_key",
        "assignment_ids", "group_ids", "allowed_slots", "weight", "members",
    )

    def __init__(self, index, unit_id, kind, label, periods, class_indexes,
                 teacher_indexes, subject_key, assignment_ids, group_ids,
                 members=()):
        self.index = index
        self.unit_id = unit_id
        self.kind = kind                    # "class" | "band"
        self.label = label
        self.periods = periods
        self.class_indexes = tuple(class_indexes)
        self.teacher_indexes = tuple(teacher_indexes)
        self.subject_key = subject_key      # used for spread scoring
        self.assignment_ids = tuple(assignment_ids)
        self.group_ids = tuple(group_ids)
        self.allowed_slots = ()             # slots where every teacher is free
        self.weight = periods               # heavier subjects want better slots
        # What each teacher in this unit is actually doing. A class lesson has
        # one member; a band has one per group, so a teacher's own timetable
        # can name the language and group instead of just "Second Language".
        self.members = tuple(members)

    def __repr__(self):
        return "<Unit %s %s x%d>" % (self.unit_id, self.label, self.periods)


class TimetableProblem:
    """Index-based view of one timetabling instance."""

    # ---------------------------------------------------------------- build

    @classmethod
    def from_dataset(cls, dataset: dict) -> "TimetableProblem":
        self = cls()
        structure = dataset["timetable_structure"]

        # --- time grid ----------------------------------------------------
        self.days = list(structure["working_days"])
        self.periods = list(structure["periods"])
        self.periods_per_day = len(self.periods)
        self.lunch_after_period = structure["lunch_after_period"]
        self.periods_before_lunch = list(structure["periods_before_lunch"])

        self.slots = [(day, period) for day in self.days for period in self.periods]
        self.n_slots = len(self.slots)
        self.slot_priority = [
            structure["period_priority"][period] for _day, period in self.slots
        ]
        self.slots_by_day = [
            list(range(d * self.periods_per_day, (d + 1) * self.periods_per_day))
            for d in range(len(self.days))
        ]

        # --- classes ------------------------------------------------------
        self.classes = list(dataset["classes"])
        self.class_ids = [c["class_id"] for c in self.classes]
        self.class_index = {cid: i for i, cid in enumerate(self.class_ids)}
        self.class_names = [c["name"] for c in self.classes]

        # --- teachers -----------------------------------------------------
        self.teachers = list(dataset["teachers"])
        self.teacher_ids = [t["teacher_id"] for t in self.teachers]
        self.teacher_index = {tid: i for i, tid in enumerate(self.teacher_ids)}
        self.teacher_names = [t["name"] for t in self.teachers]
        self.teacher_max_periods = [t["max_weekly_periods"] for t in self.teachers]

        slot_of = {slot: i for i, slot in enumerate(self.slots)}
        self.teacher_available = []
        for teacher in self.teachers:
            free = [False] * self.n_slots
            for day, day_periods in teacher["availability"].items():
                for period in day_periods:
                    index = slot_of.get((day, period))
                    if index is not None:
                        free[index] = True
            self.teacher_available.append(free)

        # class teacher of each class, as a teacher index (or None)
        self.class_teacher_index = [
            self.teacher_index.get(c.get("class_teacher_id")) for c in self.classes
        ]

        # --- subjects and requirements ------------------------------------
        self.subject_name = {
            s["subject_id"]: s["name"] for s in dataset["subjects"]
        }
        self.language_slot_subject_ids = {
            s["subject_id"] for s in dataset["subjects"] if s["is_language_slot"]
        }

        # required weekly periods per class, and the second-language reservation
        self.class_required_periods = [0] * len(self.classes)
        self.class_language_periods = [0] * len(self.classes)
        # the per-subject requirement rows, kept so a solution can be checked
        # subject by subject rather than only in total
        self.class_subject_requirements = [[] for _ in self.classes]
        for row in dataset["class_subjects"]:
            c = self.class_index[row["class_id"]]
            self.class_required_periods[c] += row["weekly_periods"]
            if row.get("taught_in_language_groups"):
                self.class_language_periods[c] += row["weekly_periods"]
            self.class_subject_requirements[c].append({
                "subject": row["subject_name"],
                "required_periods": row["weekly_periods"],
                "taught_in_language_groups": bool(
                    row.get("taught_in_language_groups")
                ),
            })

        # teacher eligibility, straight from the skill matrix
        self.teacher_skills = defaultdict(set)
        for row in dataset["teacher_subjects"]:
            self.teacher_skills[row["teacher_id"]].add(row["subject_id"])

        self._build_units(dataset)
        self._precompute_scoring_bounds()
        return self

    # ------------------------------------------------------------- units

    def _build_units(self, dataset: dict) -> None:
        """Turn teaching assignments into schedulable units."""
        assignments = dataset["teaching_assignments"]
        groups = {g["language_group_id"]: g for g in dataset["language_groups"]}

        class_assignments = [a for a in assignments if a["target_type"] == "class"]
        group_assignments = [a for a in assignments
                             if a["target_type"] == "language_group"]

        self.units = []
        self.eligibility_violations = []

        # --- one unit per class assignment ---------------------------------
        for assignment in class_assignments:
            teacher_id = assignment["teacher_id"]
            if assignment["subject_id"] not in self.teacher_skills[teacher_id]:
                self.eligibility_violations.append(
                    "%s: %s cannot teach %s"
                    % (assignment["assignment_id"], teacher_id,
                       assignment["subject_name"])
                )

            index = len(self.units)
            self.units.append(Unit(
                index=index,
                unit_id=assignment["assignment_id"],
                kind="class",
                label="%s %s" % (assignment["target_id"],
                                 assignment["subject_name"]),
                periods=assignment["weekly_periods"],
                class_indexes=[self.class_index[assignment["target_id"]]],
                teacher_indexes=[self.teacher_index[teacher_id]],
                subject_key=assignment["subject_name"],
                assignment_ids=[assignment["assignment_id"]],
                group_ids=[],
                members=[{
                    "assignment_id": assignment["assignment_id"],
                    "teacher_id": teacher_id,
                    "subject": assignment["subject_name"],
                    "target_type": "class",
                    "target_id": assignment["target_id"],
                    "group_id": None,
                }],
            ))

        # --- language groups: link groups that share a class into bands -----
        parent = {a["target_id"]: a["target_id"] for a in group_assignments}

        def find(node):
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        def union(a, b):
            root_a, root_b = find(a), find(b)
            if root_a != root_b:
                parent[root_a] = root_b

        groups_of_class = defaultdict(list)
        for assignment in group_assignments:
            for class_id in groups[assignment["target_id"]]["class_ids"]:
                groups_of_class[class_id].append(assignment["target_id"])
        for shared in groups_of_class.values():
            for other in shared[1:]:
                union(shared[0], other)

        band_members = defaultdict(list)
        for assignment in group_assignments:
            band_members[find(assignment["target_id"])].append(assignment)

        self.band_conflicts = []
        for number, (_root, members) in enumerate(sorted(band_members.items()), 1):
            members.sort(key=lambda a: a["target_id"])

            periods = {a["weekly_periods"] for a in members}
            if len(periods) > 1:
                self.band_conflicts.append(
                    "band %d mixes groups of different lengths: %s"
                    % (number, sorted(periods))
                )

            teacher_ids = [a["teacher_id"] for a in members]
            for teacher_id in sorted(set(teacher_ids)):
                if teacher_ids.count(teacher_id) > 1:
                    owned = [a["target_id"] for a in members
                             if a["teacher_id"] == teacher_id]
                    self.band_conflicts.append(
                        "band %d needs %s in %d places at once (groups %s)"
                        % (number, teacher_id, len(owned), ", ".join(owned))
                    )

            class_indexes = sorted({
                self.class_index[class_id]
                for a in members
                for class_id in groups[a["target_id"]]["class_ids"]
            })

            for teacher_id, assignment in zip(teacher_ids, members):
                if assignment["subject_id"] not in self.teacher_skills[teacher_id]:
                    self.eligibility_violations.append(
                        "%s: %s cannot teach %s"
                        % (assignment["assignment_id"], teacher_id,
                           assignment["subject_name"])
                    )

            index = len(self.units)
            self.units.append(Unit(
                index=index,
                unit_id="BAND-%02d" % number,
                kind="band",
                label="Second Language band %d (%s)"
                      % (number, ", ".join(a["subject_name"] for a in members)),
                periods=max(periods),
                class_indexes=class_indexes,
                teacher_indexes=[self.teacher_index[t] for t in teacher_ids],
                subject_key="Second Language",
                assignment_ids=[a["assignment_id"] for a in members],
                group_ids=[a["target_id"] for a in members],
                members=[{
                    "assignment_id": a["assignment_id"],
                    "teacher_id": a["teacher_id"],
                    "subject": a["subject_name"],
                    "target_type": "language_group",
                    "target_id": a["target_id"],
                    "group_id": a["target_id"],
                } for a in members],
            ))

        # --- derived indexes ----------------------------------------------
        for unit in self.units:
            unit.allowed_slots = tuple(
                slot for slot in range(self.n_slots)
                if all(self.teacher_available[t][slot] for t in unit.teacher_indexes)
            )

        self.band_unit_indexes = [u.index for u in self.units if u.kind == "band"]
        self.class_unit_indexes = [[] for _ in self.classes]
        for unit in self.units:
            if unit.kind == "class":
                self.class_unit_indexes[unit.class_indexes[0]].append(unit.index)

        # every unit touching a class, bands included
        self.units_of_class = [[] for _ in self.classes]
        for unit in self.units:
            for c in unit.class_indexes:
                self.units_of_class[c].append(unit.index)

        self.units_of_teacher = [[] for _ in self.teachers]
        for unit in self.units:
            for t in unit.teacher_indexes:
                self.units_of_teacher[t].append(unit.index)

        # band periods each class owes, used to validate band scheduling
        self.class_band_periods = [0] * len(self.classes)
        for index in self.band_unit_indexes:
            unit = self.units[index]
            for c in unit.class_indexes:
                self.class_band_periods[c] += unit.periods

    # -------------------------------------------------- scoring bounds

    def _precompute_scoring_bounds(self) -> None:
        """Fixed bounds so soft scores can be reported on a 0..1 scale."""
        # Period priority: each class's lesson weights are fixed, so the best
        # and worst possible weight/priority pairings can be computed once.
        best = worst = 0.0
        for c in range(len(self.classes)):
            weights = []
            for index in self.units_of_class[c]:
                unit = self.units[index]
                weights.extend([unit.weight] * unit.periods)
            weights.sort(reverse=True)

            priorities = sorted(self.slot_priority, reverse=True)[:len(weights)]
            best += sum(w * p for w, p in zip(weights, priorities))
            priorities = sorted(self.slot_priority)[:len(weights)]
            worst += sum(w * p for w, p in zip(weights, priorities))

        self.priority_best = best
        self.priority_worst = worst

        # Class teacher / first period: how many mornings could the class
        # teacher realistically open, given how much they teach that class.
        self.class_teacher_opportunities = []
        for c in range(len(self.classes)):
            teacher = self.class_teacher_index[c]
            periods = 0
            if teacher is not None:
                for index in self.class_unit_indexes[c]:
                    if teacher in self.units[index].teacher_indexes:
                        periods += self.units[index].periods
            self.class_teacher_opportunities.append(min(len(self.days), periods))

        self.total_lessons = sum(unit.periods for unit in self.units)
        self.total_class_lessons = sum(
            unit.periods * len(unit.class_indexes) for unit in self.units
        )

        # Crude but stable denominators for the penalty-style soft scores.
        self.max_repeat_penalty = max(
            1, len(self.classes) * len(self.days) * (self.periods_per_day - 1)
        )
        self.max_gap_penalty = max(
            1, len(self.teachers) * len(self.days) * (self.periods_per_day - 2)
        )

    # ------------------------------------------------------- feasibility

    def feasibility_issues(self) -> list:
        """Problems no schedule could ever fix. Empty list means solvable.

        These are checked before evolution, because a GA cannot repair a
        dataset that asks for more than the week can hold.
        """
        issues = []

        for violation in self.eligibility_violations:
            issues.append("teacher eligibility - %s" % violation)

        for conflict in self.band_conflicts:
            issues.append("language band - %s" % conflict)

        for c, klass in enumerate(self.classes):
            required = sum(
                self.units[i].periods for i in self.units_of_class[c]
            )
            if required > self.n_slots:
                issues.append(
                    "class %s needs %d periods but the week has %d slots"
                    % (klass["class_id"], required, self.n_slots)
                )
            if self.class_band_periods[c] != self.class_language_periods[c]:
                issues.append(
                    "class %s reserves %d second-language periods but its "
                    "bands supply %d"
                    % (klass["class_id"], self.class_language_periods[c],
                       self.class_band_periods[c])
                )

        for t, teacher in enumerate(self.teachers):
            load = sum(self.units[i].periods for i in self.units_of_teacher[t])
            available = sum(1 for free in self.teacher_available[t] if free)
            if load > self.teacher_max_periods[t]:
                issues.append(
                    "teacher %s is assigned %d periods but may teach %d"
                    % (teacher["teacher_id"], load, self.teacher_max_periods[t])
                )
            if load > available:
                issues.append(
                    "teacher %s is assigned %d periods but is available for %d"
                    % (teacher["teacher_id"], load, available)
                )

        for unit in self.units:
            if len(unit.allowed_slots) < unit.periods:
                issues.append(
                    "%s needs %d slots but its teachers share only %d free ones"
                    % (unit.unit_id, unit.periods, len(unit.allowed_slots))
                )

        issues.extend(self._dead_slot_issues())
        return issues

    def _dead_slot_issues(self) -> list:
        """Catch slots a class simply cannot fill.

        If no teacher of a class is ever available at some slot, only the
        second-language band can cover it - and a band is one set of slots
        shared by every class in it. So the band has to cover the dead slots
        of all its classes at once, which is impossible past its own length.

        Without this check a solver just grinds away one clash short of a
        solution, because no rearrangement can ever fix the data.
        """
        issues = []

        dead_slots = []
        for c in range(len(self.classes)):
            coverable = [False] * self.n_slots
            for index in self.class_unit_indexes[c]:
                for t in self.units[index].teacher_indexes:
                    for slot in range(self.n_slots):
                        if self.teacher_available[t][slot]:
                            coverable[slot] = True
            dead_slots.append(
                {slot for slot in range(self.n_slots) if not coverable[slot]}
            )

            required = sum(self.units[i].periods for i in self.class_unit_indexes[c])
            band_periods = self.class_band_periods[c]
            usable = self.n_slots - len(dead_slots[c])
            usable -= max(0, band_periods - len(dead_slots[c]))
            if required > usable:
                issues.append(
                    "class %s needs %d teachable slots but only %d of the week "
                    "are covered by a teacher it has"
                    % (self.class_ids[c], required, usable)
                )

        for index in self.band_unit_indexes:
            unit = self.units[index]
            must_cover = set()
            for c in unit.class_indexes:
                must_cover |= dead_slots[c]

            if len(must_cover) > unit.periods:
                issues.append(
                    "%s runs %d periods but must cover %d slots that its "
                    "classes cannot fill any other way (%s)"
                    % (unit.unit_id, unit.periods, len(must_cover),
                       ", ".join(sorted(self.slot_name(s) for s in must_cover)))
                )

            outside = must_cover - set(unit.allowed_slots)
            if outside:
                issues.append(
                    "%s must cover %s, but its own teachers are not available "
                    "then" % (unit.unit_id,
                              ", ".join(sorted(self.slot_name(s) for s in outside)))
                )

        return issues

    # ------------------------------------------------------------ helpers

    def day_of(self, slot: int) -> int:
        return slot // self.periods_per_day

    def period_of(self, slot: int) -> int:
        return slot % self.periods_per_day

    def slot_name(self, slot: int) -> str:
        day, period = self.slots[slot]
        return "%s %s" % (day, period)

    def describe(self) -> str:
        return (
            "%d classes, %d teachers, %d units, %d lessons to place, "
            "%d slots (%d days x %d periods), %d language band(s)"
            % (len(self.classes), len(self.teachers), len(self.units),
               self.total_lessons, self.n_slots, len(self.days),
               self.periods_per_day, len(self.band_unit_indexes))
        )
