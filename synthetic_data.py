"""
synthetic_data.py
-----------------
Synthetic data generator for V1 of the multi-class GA timetable system.

Produces one realistic, internally consistent, reproducible relational
dataset for a Kerala Higher Secondary school:

    academic year -> classes -> students -> second-language choices
                  -> language groups (students from several classes)
                  -> subjects -> class-subject requirements
                  -> teachers -> teacher-subject skills
                  -> teaching assignments (teacher + target + subject)

Everything is plain dicts and lists, generated from a fixed seed, and the
result can be dumped straight to JSON.

Independent by design: no GA, no Laravel, no database, no API, no imports
from the Phase 1 prototype files. The only imports are from the standard
library.

Run:  python synthetic_data.py          # generates, validates, writes JSON
"""

from __future__ import annotations

import json
import math
import os
import random
from collections import defaultdict

# ===========================================================================
# 1. CONFIGURATION - everything tunable lives here
# ===========================================================================

CONFIG = {
    # Reproducibility. The same seed always yields the same dataset.
    "seed": 20250904,

    "academic_year": {
        "name": "2025-2026",
        "start_date": "2025-06-02",
        "end_date": "2026-03-31",
    },

    # Classes. V1 is specified for 8-12 classes; the range is validated.
    "num_classes": 10,
    "supported_class_range": (8, 12),

    # Students per class, inclusive range - each class draws its own strength.
    "students_per_class": (38, 52),

    # Timetable frame: 5 days x 7 periods = 35 slots. Lunch sits between
    # P4 and P5 and is NOT a period, so it consumes no slot.
    "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    "periods": ["P1", "P2", "P3", "P4", "P5", "P6", "P7"],
    "periods_before_lunch": ["P1", "P2", "P3", "P4"],
    "lunch_after_period": "P4",

    # Priority / desirability of each period. Higher = more desirable.
    # Morning is deliberately not assumed to be inherently better.
    "period_priority": {
        "P1": 7,
        "P2": 9,
        "P3": 9,
        "P4": 8,
        "P5": 6,
        "P6": 8,
        "P7": 5,
    },

    # Second language: how many periods a week, and how students choose.
    # Weights need not sum to 1; they are normalised.
    #
    # NOTE: the stream templates below already fill all 35 weekly slots, so
    # changing this number means taking the difference off another subject
    # in STREAM_TEMPLATES. Validation reports it if you forget.
    "second_language_periods": 4,
    "second_language_popularity": {
        "Malayalam": 0.45,
        "Hindi": 0.30,
        "Sanskrit": 0.15,
        "French": 0.10,
    },

    # A language group pools students from several classes who chose the
    # same second language. Groups are split once they exceed this size.
    "max_language_group_size": 45,

    # Teachers. The number of teachers per department is derived from the
    # actual teaching demand (so the dataset is always feasible), then
    # padded by the values below.
    "teacher_max_weekly_periods": (20, 26),
    "teacher_unavailable_slots": (0, 3),
    "min_teachers_per_department": 1,
    # Spare staff per department. 0 keeps workloads realistic; raise it to
    # model a school with slack. Understaffing is repaired automatically.
    "extra_teachers_per_department": 0,

    # Safety valve for the assignment retry loop (see assign_teaching_loads).
    "max_assignment_attempts": 30,
}

# ---------------------------------------------------------------------------
# Subject catalogue
#
# "Second Language" is a placeholder subject: it reserves periods in every
# class timetable, but nobody teaches "Second Language" as such. The real
# teaching happens in parallel language groups (Malayalam / Hindi / ...),
# which is why the placeholder has no department.
#
# type is one of: "language", "core", "elective".
# ---------------------------------------------------------------------------

SECOND_LANGUAGE_SLOT = "Second Language"

SUBJECT_CATALOG = [
    # name, type, is_second_language, is_language_slot, department
    ("English", "language", False, False, "English"),
    (SECOND_LANGUAGE_SLOT, "language", True, True, None),
    ("Malayalam", "language", True, False, "Malayalam"),
    ("Hindi", "language", True, False, "Hindi"),
    ("Sanskrit", "language", True, False, "Sanskrit"),
    ("French", "language", True, False, "French"),
    ("Physics", "core", False, False, "Physics"),
    ("Chemistry", "core", False, False, "Chemistry"),
    ("Mathematics", "core", False, False, "Mathematics"),
    ("Biology", "core", False, False, "Biology"),
    ("Computer Science", "core", False, False, "Computer Science"),
    ("Computer Application", "elective", False, False, "Computer Science"),
    ("Business Studies", "core", False, False, "Commerce"),
    ("Accountancy", "core", False, False, "Commerce"),
    ("Economics", "core", False, False, "Economics"),
    ("History", "core", False, False, "Social Science"),
    ("Political Science", "core", False, False, "Social Science"),
    ("Sociology", "elective", False, False, "Social Science"),
]

# ---------------------------------------------------------------------------
# Stream templates: the weekly period requirement of each class.
#
# The Second Language entry is filled in from CONFIG at build time, so the
# number of second-language periods has exactly one source of truth.
# Each template is validated to fill the 35 available slots.
# ---------------------------------------------------------------------------

STREAM_TEMPLATES = {
    "science_cs": {
        "label": "Science (Computer Science)",
        "subjects": {
            "English": 5,
            SECOND_LANGUAGE_SLOT: None,   # from CONFIG["second_language_periods"]
            "Physics": 6,
            "Chemistry": 6,
            "Mathematics": 7,
            "Computer Science": 7,
        },
    },
    "science_bio": {
        "label": "Science (Biology)",
        "subjects": {
            "English": 5,
            SECOND_LANGUAGE_SLOT: None,
            "Physics": 6,
            "Chemistry": 6,
            "Biology": 7,
            "Mathematics": 7,
        },
    },
    "commerce": {
        "label": "Commerce",
        "subjects": {
            "English": 5,
            SECOND_LANGUAGE_SLOT: None,
            "Business Studies": 7,
            "Accountancy": 7,
            "Economics": 6,
            "Computer Application": 6,
        },
    },
    "humanities": {
        "label": "Humanities",
        "subjects": {
            "English": 5,
            SECOND_LANGUAGE_SLOT: None,
            "History": 7,
            "Political Science": 7,
            "Economics": 6,
            "Sociology": 6,
        },
    },
}

# Classes are handed out in this order, cycling as needed.
STREAM_ROTATION = ["science_cs", "science_bio", "commerce", "humanities"]

# Name pools, kept small on purpose - combined they give plenty of variety.
FIRST_NAMES = [
    "Aiswarya", "Anagha", "Anjali", "Arun", "Athira", "Bhavana", "Deepak",
    "Devika", "Divya", "Fathima", "Gopika", "Harikrishnan", "Indu", "Jithin",
    "Kavya", "Lakshmi", "Manu", "Meera", "Nandana", "Nikhil", "Nithya",
    "Parvathy", "Praveen", "Rahul", "Reshma", "Rohit", "Sandeep", "Sneha",
    "Sreejith", "Sujith", "Vishnu", "Vivek",
]

LAST_NAMES = [
    "Nair", "Menon", "Pillai", "Kurup", "Varma", "Thomas", "Joseph",
    "Mathew", "George", "Krishnan", "Raj", "Das", "Mohan", "Sasidharan",
    "Unnikrishnan", "Suresh", "Bhaskaran", "Chandran",
]


# ===========================================================================
# 2. SMALL HELPERS
# ===========================================================================

def make_id(prefix: str, number: int, width: int = 2) -> str:
    """Readable stable id, e.g. make_id('CLS', 3) -> 'CLS-03'."""
    return "%s-%0*d" % (prefix, width, number)


def pick_name(rng: random.Random) -> str:
    return "%s %s" % (rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES))


def weighted_choice(rng: random.Random, weights: dict) -> str:
    """Pick a key from {key: weight}. Weights need not be normalised."""
    keys = sorted(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def split_evenly(items: list, max_size: int) -> list:
    """Split a list into the fewest chunks of at most max_size, balanced."""
    if not items:
        return []
    chunk_count = max(1, math.ceil(len(items) / max_size))
    base, extra = divmod(len(items), chunk_count)
    chunks = []
    start = 0
    for index in range(chunk_count):
        size = base + (1 if index < extra else 0)
        chunks.append(items[start:start + size])
        start += size
    return chunks


# ===========================================================================
# 3. GENERATION - one function per entity, called in dependency order
# ===========================================================================

def build_academic_year(config: dict) -> dict:
    year = config["academic_year"]
    return {
        "academic_year_id": make_id("AY", 1),
        "name": year["name"],
        "start_date": year["start_date"],
        "end_date": year["end_date"],
    }


def build_timetable_structure(config: dict) -> dict:
    """Days, periods, lunch position, the 35 slots and period priorities."""
    days = config["working_days"]
    periods = config["periods"]
    before_lunch = config["periods_before_lunch"]
    after_lunch = [p for p in periods if p not in before_lunch]

    slots = [
        {"slot_id": make_id("SLOT", i + 1), "day": day, "period": period,
         "priority": config["period_priority"][period]}
        for i, (day, period) in enumerate(
            (day, period) for day in days for period in periods
        )
    ]

    return {
        "working_days": days,
        "periods": periods,
        "periods_before_lunch": before_lunch,
        "periods_after_lunch": after_lunch,
        "lunch_after_period": config["lunch_after_period"],
        "lunch_is_a_period": False,
        "periods_per_day": len(periods),
        "total_weekly_slots": len(days) * len(periods),
        "period_priority": dict(config["period_priority"]),
        "slots": slots,
    }


def build_subjects() -> tuple:
    """Return (subjects, subject_id_by_name)."""
    subjects = []
    by_name = {}

    for index, (name, kind, is_second, is_slot, department) in enumerate(
        SUBJECT_CATALOG, start=1
    ):
        subject_id = make_id("SUB", index)
        subjects.append({
            "subject_id": subject_id,
            "name": name,
            "type": kind,
            "is_second_language": is_second,
            # True only for the placeholder that reserves the shared slot.
            "is_language_slot": is_slot,
            "department": department,
        })
        by_name[name] = subject_id

    return subjects, by_name


def build_classes(config: dict, rng: random.Random) -> list:
    """Classes with stream, section and student strength (teacher added later)."""
    classes = []
    section_counter = defaultdict(int)

    for index in range(config["num_classes"]):
        stream = STREAM_ROTATION[index % len(STREAM_ROTATION)]
        section_counter[stream] += 1
        section = chr(ord("A") + section_counter[stream] - 1)
        template = STREAM_TEMPLATES[stream]

        low, high = config["students_per_class"]
        classes.append({
            "class_id": make_id("CLS", index + 1),
            "name": "+2 %s - %s" % (template["label"], section),
            "section": section,
            "stream": stream,
            "stream_label": template["label"],
            "student_strength": rng.randint(low, high),
            "class_teacher_id": None,   # filled by assign_class_teachers()
        })

    return classes


def build_students(classes: list, config: dict, rng: random.Random) -> list:
    """One student per seat, each with a second-language choice."""
    students = []
    counter = 0

    for klass in classes:
        for roll_no in range(1, klass["student_strength"] + 1):
            counter += 1
            students.append({
                "student_id": make_id("STU", counter, width=4),
                "name": pick_name(rng),
                "class_id": klass["class_id"],
                "roll_no": roll_no,
                "second_language": weighted_choice(
                    rng, config["second_language_popularity"]
                ),
            })

    return students


def build_class_subjects(classes: list, subject_id_by_name: dict,
                         config: dict) -> list:
    """Weekly period requirement of every class, straight from its template."""
    class_subjects = []
    counter = 0

    for klass in classes:
        template = STREAM_TEMPLATES[klass["stream"]]["subjects"]

        for subject_name, periods in template.items():
            if periods is None:      # the Second Language placeholder
                periods = config["second_language_periods"]

            counter += 1
            class_subjects.append({
                "class_subject_id": make_id("CS", counter, width=3),
                "class_id": klass["class_id"],
                "subject_id": subject_id_by_name[subject_name],
                "subject_name": subject_name,
                "weekly_periods": periods,
                # True for the shared slot taught in language groups.
                "taught_in_language_groups":
                    subject_name == SECOND_LANGUAGE_SLOT,
            })

    return class_subjects


def build_language_groups(students: list, classes: list,
                          subject_id_by_name: dict, config: dict) -> list:
    """Pool students who chose the same second language into groups.

    Students are ordered by class before splitting, so a group naturally
    draws from a few neighbouring classes rather than from all of them.
    Group strength always equals its member count and its class-wise counts.
    """
    class_order = {klass["class_id"]: i for i, klass in enumerate(classes)}

    by_language = defaultdict(list)
    for student in students:
        by_language[student["second_language"]].append(student)

    groups = []
    counter = 0

    for language in sorted(by_language):
        members = sorted(
            by_language[language],
            key=lambda s: (class_order[s["class_id"]], s["roll_no"]),
        )

        for chunk in split_evenly(members, config["max_language_group_size"]):
            counter += 1

            class_distribution = defaultdict(int)
            for student in chunk:
                class_distribution[student["class_id"]] += 1

            groups.append({
                "language_group_id": make_id("LG", counter),
                "name": "%s Group %d" % (language, counter),
                "language": language,
                "subject_id": subject_id_by_name[language],
                "weekly_periods": config["second_language_periods"],
                "strength": len(chunk),
                # How many of the members come from each class.
                "class_distribution": dict(sorted(class_distribution.items())),
                "class_ids": sorted(class_distribution),
                "student_ids": [s["student_id"] for s in chunk],
            })

    return groups


# ---------------------------------------------------------------------------
# Teaching demand -> teachers -> assignments
#
# Teachers are generated AFTER the demand is known, so the dataset is
# feasible by construction: a department can never be short of capacity.
# ---------------------------------------------------------------------------

def build_demand_items(class_subjects: list, language_groups: list,
                       classes: list, subjects_by_id: dict) -> list:
    """Every unit of teaching that needs a teacher.

    One item per class-subject (excluding the shared second-language slot)
    plus one item per language group.
    """
    class_name_by_id = {c["class_id"]: c["name"] for c in classes}
    items = []

    for row in class_subjects:
        if row["taught_in_language_groups"]:
            continue        # covered by the language-group items below
        items.append({
            "subject_id": row["subject_id"],
            "subject_name": row["subject_name"],
            "target_type": "class",
            "target_id": row["class_id"],
            "target_name": class_name_by_id[row["class_id"]],
            "weekly_periods": row["weekly_periods"],
            "class_subject_id": row["class_subject_id"],
        })

    for group in language_groups:
        items.append({
            "subject_id": group["subject_id"],
            "subject_name": subjects_by_id[group["subject_id"]]["name"],
            "target_type": "language_group",
            "target_id": group["language_group_id"],
            "target_name": group["name"],
            "weekly_periods": group["weekly_periods"],
            "class_subject_id": None,
        })

    return items


def department_demand(demand_items: list, subjects_by_id: dict) -> dict:
    """Weekly periods needed per department."""
    totals = defaultdict(int)
    for item in demand_items:
        department = subjects_by_id[item["subject_id"]]["department"]
        totals[department] += item["weekly_periods"]
    return dict(totals)


def build_teachers(demand_items: list, subjects_by_id: dict, subjects: list,
                   config: dict, rng: random.Random,
                   extra_per_department: dict | None = None) -> tuple:
    """Create teachers per department, sized to cover the demand.

    Returns (teachers, teacher_subjects). Each teacher can teach every
    subject of their department, which keeps the skill matrix realistic
    for a school of this size and guarantees the demand is coverable.
    """
    extra_per_department = extra_per_department or {}

    subjects_by_department = defaultdict(list)
    for subject in subjects:
        if subject["department"]:
            subjects_by_department[subject["department"]].append(subject)

    demand = department_demand(demand_items, subjects_by_id)
    low_capacity, high_capacity = config["teacher_max_weekly_periods"]

    days = config["working_days"]
    periods = config["periods"]
    total_slots = len(days) * len(periods)
    min_unavailable, max_unavailable = config["teacher_unavailable_slots"]

    teachers = []
    teacher_subjects = []
    counter = 0

    for department in sorted(subjects_by_department):
        needed_periods = demand.get(department, 0)

        # Size the department from its demand. Dividing by the largest
        # allowed load keeps staffing tight and workloads realistic; if a
        # department turns out to be short, assign_teaching_loads() adds a
        # teacher and regenerates rather than shipping a broken dataset.
        headcount = max(
            config["min_teachers_per_department"],
            math.ceil(needed_periods / high_capacity)
            + config["extra_teachers_per_department"]
            + extra_per_department.get(department, 0),
        )

        for _ in range(headcount):
            counter += 1
            teacher_id = make_id("TCH", counter)

            # Availability: block a few random slots (leave, duty, etc.).
            blocked_count = rng.randint(min_unavailable, max_unavailable)
            blocked = set()
            while len(blocked) < blocked_count:
                blocked.add((rng.choice(days), rng.choice(periods)))

            availability = {
                day: [p for p in periods if (day, p) not in blocked]
                for day in days
            }
            available_count = total_slots - len(blocked)

            # A teacher can never be asked to work more than they are free.
            max_weekly = min(rng.randint(low_capacity, high_capacity),
                             available_count)

            teachers.append({
                "teacher_id": teacher_id,
                "name": pick_name(rng),
                "department": department,
                "max_weekly_periods": max_weekly,
                "availability": availability,
                "unavailable_slots": [
                    {"day": day, "period": period}
                    for day, period in sorted(blocked)
                ],
                "available_period_count": available_count,
                "assigned_weekly_periods": 0,   # filled after assignment
            })

            for subject in subjects_by_department[department]:
                teacher_subjects.append({
                    "teacher_id": teacher_id,
                    "subject_id": subject["subject_id"],
                    "subject_name": subject["name"],
                })

    return teachers, teacher_subjects


def try_assign(demand_items: list, teachers: list,
               teacher_subjects: list) -> list | None:
    """Greedily give every demand item a qualified teacher.

    Returns the assignment list, or None if some item found no teacher
    with enough remaining capacity (the caller then adds staff and retries).
    Heaviest items are placed first, and the least-loaded qualified teacher
    wins, which spreads the load evenly.
    """
    can_teach = defaultdict(set)
    for row in teacher_subjects:
        can_teach[row["subject_id"]].add(row["teacher_id"])

    teacher_by_id = {t["teacher_id"]: t for t in teachers}
    remaining = {t["teacher_id"]: t["max_weekly_periods"] for t in teachers}

    ordered = sorted(
        demand_items,
        key=lambda item: (-item["weekly_periods"], item["subject_name"],
                          item["target_id"]),
    )

    assignments = []
    counter = 0

    for item in ordered:
        candidates = [
            teacher_id for teacher_id in sorted(can_teach[item["subject_id"]])
            if remaining[teacher_id] >= item["weekly_periods"]
        ]
        if not candidates:
            return None

        # Most remaining capacity first -> balanced workloads.
        chosen = max(candidates, key=lambda tid: (remaining[tid], tid))
        remaining[chosen] -= item["weekly_periods"]

        counter += 1
        assignments.append({
            "assignment_id": make_id("ASG", counter, width=3),
            "teacher_id": chosen,
            "teacher_name": teacher_by_id[chosen]["name"],
            "subject_id": item["subject_id"],
            "subject_name": item["subject_name"],
            "target_type": item["target_type"],      # class | language_group
            "target_id": item["target_id"],
            "target_name": item["target_name"],
            "weekly_periods": item["weekly_periods"],
            "class_subject_id": item["class_subject_id"],
        })

    assignments.sort(key=lambda a: a["assignment_id"])
    return assignments


def assign_teaching_loads(demand_items, subjects_by_id, subjects, config, seed):
    """Build teachers and assignments together, adding staff until it fits.

    The greedy pass can fail if one department happens to be understaffed
    for the drawn demand. Rather than leaving a broken dataset, another
    teacher is added to the failing department and the whole staffing pass
    is repeated from the same seed - so the result stays reproducible.
    """
    extra_per_department = defaultdict(int)

    for _attempt in range(config["max_assignment_attempts"]):
        # Always the same seed, so the retry loop stays reproducible.
        rng = random.Random(seed)
        teachers, teacher_subjects = build_teachers(
            demand_items, subjects_by_id, subjects, config, rng,
            extra_per_department=dict(extra_per_department),
        )

        assignments = try_assign(demand_items, teachers, teacher_subjects)
        if assignments is not None:
            load = defaultdict(int)
            for assignment in assignments:
                load[assignment["teacher_id"]] += assignment["weekly_periods"]
            for teacher in teachers:
                teacher["assigned_weekly_periods"] = load[teacher["teacher_id"]]
            return teachers, teacher_subjects, assignments

        # Find the department that ran out of capacity and staff it up.
        short = find_short_department(demand_items, teachers, teacher_subjects,
                                      subjects_by_id)
        extra_per_department[short] += 1

    raise RuntimeError(
        "Could not staff the timetable in %d attempts - check the teacher "
        "capacity settings in CONFIG." % config["max_assignment_attempts"]
    )


def find_short_department(demand_items, teachers, teacher_subjects,
                          subjects_by_id) -> str:
    """The department whose capacity is tightest against its demand."""
    capacity = defaultdict(int)
    for teacher in teachers:
        capacity[teacher["department"]] += teacher["max_weekly_periods"]

    demand = department_demand(demand_items, subjects_by_id)
    return min(demand, key=lambda dept: capacity.get(dept, 0) - demand[dept])


def assign_class_teachers(classes: list, assignments: list,
                          teachers: list) -> None:
    """Give every class a class teacher who actually teaches that class.

    A teacher is class teacher of at most one class. If every teacher of a
    class is already taken, the least loaded free teacher steps in.
    """
    teachers_of_class = defaultdict(list)
    for assignment in assignments:
        if assignment["target_type"] == "class":
            teachers_of_class[assignment["target_id"]].append(
                assignment["teacher_id"]
            )

    load_by_id = {t["teacher_id"]: t["assigned_weekly_periods"] for t in teachers}
    taken = set()

    for klass in classes:
        candidates = [
            tid for tid in sorted(set(teachers_of_class[klass["class_id"]]))
            if tid not in taken
        ]
        if not candidates:
            candidates = [
                t["teacher_id"] for t in teachers if t["teacher_id"] not in taken
            ]

        chosen = min(candidates, key=lambda tid: (load_by_id[tid], tid))
        taken.add(chosen)
        klass["class_teacher_id"] = chosen


# ===========================================================================
# 4. DATASET ASSEMBLY
# ===========================================================================

def build_dataset(config: dict = CONFIG) -> dict:
    """Generate the whole dataset, hierarchically and reproducibly."""
    seed = config["seed"]
    rng = random.Random(seed)

    academic_year = build_academic_year(config)
    timetable_structure = build_timetable_structure(config)

    subjects, subject_id_by_name = build_subjects()
    subjects_by_id = {s["subject_id"]: s for s in subjects}

    second_language_options = [
        {
            "subject_id": subject_id_by_name[name],
            "name": name,
            "weekly_periods": config["second_language_periods"],
            "popularity_weight": weight,
        }
        for name, weight in sorted(config["second_language_popularity"].items())
    ]

    # classes -> students -> language groups
    classes = build_classes(config, rng)
    students = build_students(classes, config, rng)
    class_subjects = build_class_subjects(classes, subject_id_by_name, config)
    language_groups = build_language_groups(
        students, classes, subject_id_by_name, config
    )

    # demand -> teachers -> assignments -> class teachers
    demand_items = build_demand_items(
        class_subjects, language_groups, classes, subjects_by_id
    )
    teachers, teacher_subjects, teaching_assignments = assign_teaching_loads(
        demand_items, subjects_by_id, subjects, config, seed
    )
    assign_class_teachers(classes, teaching_assignments, teachers)

    dataset = {
        "meta": {
            "generator": "synthetic_data.py",
            "version": "v1",
            "seed": seed,
            "description": "Synthetic multi-class timetable dataset "
                           "(no GA, database or API dependencies).",
        },
        "config": json_safe_config(config),
        "academic_year": academic_year,
        "timetable_structure": timetable_structure,
        "subjects": subjects,
        "second_language_options": second_language_options,
        "classes": classes,
        "students": students,
        "teachers": teachers,
        "class_subjects": class_subjects,
        "teacher_subjects": teacher_subjects,
        "language_groups": language_groups,
        "teaching_assignments": teaching_assignments,
    }
    dataset["summary"] = summarise(dataset)
    return dataset


def json_safe_config(config: dict) -> dict:
    """Config copy with tuples turned into lists, so it serialises cleanly."""
    return {
        key: list(value) if isinstance(value, tuple) else value
        for key, value in config.items()
    }


def summarise(dataset: dict) -> dict:
    """Headline counts, handy for a quick sanity read of the dataset."""
    teachers = dataset["teachers"]
    loads = [t["assigned_weekly_periods"] for t in teachers]

    return {
        "classes": len(dataset["classes"]),
        "students": len(dataset["students"]),
        "teachers": len(teachers),
        "subjects": len(dataset["subjects"]),
        "class_subject_rows": len(dataset["class_subjects"]),
        "teacher_subject_rows": len(dataset["teacher_subjects"]),
        "language_groups": len(dataset["language_groups"]),
        "teaching_assignments": len(dataset["teaching_assignments"]),
        "total_weekly_slots": dataset["timetable_structure"]["total_weekly_slots"],
        "total_taught_periods": sum(
            a["weekly_periods"] for a in dataset["teaching_assignments"]
        ),
        "teacher_load": {
            "min": min(loads) if loads else 0,
            "max": max(loads) if loads else 0,
            "average": round(sum(loads) / len(loads), 1) if loads else 0,
        },
        "students_per_second_language": {
            option["name"]: sum(
                1 for s in dataset["students"]
                if s["second_language"] == option["name"]
            )
            for option in dataset["second_language_options"]
        },
    }


# ===========================================================================
# 5. VALIDATION - every rule the dataset promises to keep
# ===========================================================================

def validate_dataset(dataset: dict) -> list:
    """Return a list of problems. An empty list means the data is consistent."""
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)

    config = dataset["config"]
    structure = dataset["timetable_structure"]

    classes = dataset["classes"]
    students = dataset["students"]
    teachers = dataset["teachers"]
    subjects = dataset["subjects"]
    class_subjects = dataset["class_subjects"]
    teacher_subjects = dataset["teacher_subjects"]
    language_groups = dataset["language_groups"]
    assignments = dataset["teaching_assignments"]

    class_ids = {c["class_id"] for c in classes}
    teacher_ids = {t["teacher_id"] for t in teachers}
    subject_ids = {s["subject_id"] for s in subjects}
    group_ids = {g["language_group_id"] for g in language_groups}
    student_ids = {s["student_id"] for s in students}

    subjects_by_id = {s["subject_id"]: s for s in subjects}
    teachers_by_id = {t["teacher_id"]: t for t in teachers}
    student_by_id = {s["student_id"]: s for s in students}

    # --- 1. unique ids -----------------------------------------------------
    check(len(class_ids) == len(classes), "duplicate class_id")
    check(len(teacher_ids) == len(teachers), "duplicate teacher_id")
    check(len(subject_ids) == len(subjects), "duplicate subject_id")
    check(len(group_ids) == len(language_groups), "duplicate language_group_id")
    check(len(student_ids) == len(students), "duplicate student_id")
    check(
        len({a["assignment_id"] for a in assignments}) == len(assignments),
        "duplicate assignment_id",
    )

    # --- 2. timetable frame ------------------------------------------------
    days = structure["working_days"]
    periods = structure["periods"]
    check(len(structure["slots"]) == len(days) * len(periods),
          "slot list does not match days x periods")
    check(structure["total_weekly_slots"] == len(days) * len(periods),
          "total_weekly_slots is wrong")
    check(set(structure["period_priority"]) == set(periods),
          "period_priority must score exactly P1..P7")
    check(structure["lunch_after_period"] in periods,
          "lunch_after_period is not a known period")
    check(structure["lunch_after_period"] == structure["periods_before_lunch"][-1],
          "lunch must fall right after the last morning period")
    check(not structure["lunch_is_a_period"],
          "lunch must not count as a teaching period")

    # --- 3. classes --------------------------------------------------------
    low, high = config["supported_class_range"]
    check(low <= len(classes) <= high,
          "V1 supports %d-%d classes, found %d" % (low, high, len(classes)))

    class_teacher_ids = [c["class_teacher_id"] for c in classes]
    for klass in classes:
        check(klass["class_teacher_id"] in teacher_ids,
              "class %s has an unknown class_teacher_id" % klass["class_id"])
    check(len(set(class_teacher_ids)) == len(class_teacher_ids),
          "a teacher is class teacher of more than one class")

    # --- 4. students -------------------------------------------------------
    language_names = {o["name"] for o in dataset["second_language_options"]}
    counted = defaultdict(int)
    for student in students:
        check(student["class_id"] in class_ids,
              "student %s points at an unknown class" % student["student_id"])
        check(student["second_language"] in language_names,
              "student %s chose an unknown second language" % student["student_id"])
        counted[student["class_id"]] += 1

    for klass in classes:
        check(counted[klass["class_id"]] == klass["student_strength"],
              "class %s strength %d does not match %d students"
              % (klass["class_id"], klass["student_strength"],
                 counted[klass["class_id"]]))

    # --- 5. class subjects -------------------------------------------------
    periods_per_class = defaultdict(int)
    slot_subject_periods = {}
    for row in class_subjects:
        check(row["class_id"] in class_ids,
              "class_subject %s points at an unknown class" % row["class_subject_id"])
        check(row["subject_id"] in subject_ids,
              "class_subject %s points at an unknown subject" % row["class_subject_id"])
        check(row["weekly_periods"] > 0,
              "class_subject %s has no periods" % row["class_subject_id"])
        periods_per_class[row["class_id"]] += row["weekly_periods"]
        if row["taught_in_language_groups"]:
            slot_subject_periods[row["class_id"]] = row["weekly_periods"]

    for klass in classes:
        total = periods_per_class[klass["class_id"]]
        check(total <= structure["total_weekly_slots"],
              "class %s needs %d periods but only %d slots exist"
              % (klass["class_id"], total, structure["total_weekly_slots"]))
        check(klass["class_id"] in slot_subject_periods,
              "class %s has no second-language slot" % klass["class_id"])

    # --- 6. teacher-subject skills ----------------------------------------
    skills = defaultdict(set)
    seen_pairs = set()
    for row in teacher_subjects:
        check(row["teacher_id"] in teacher_ids,
              "teacher_subject points at an unknown teacher")
        check(row["subject_id"] in subject_ids,
              "teacher_subject points at an unknown subject")
        pair = (row["teacher_id"], row["subject_id"])
        check(pair not in seen_pairs, "duplicate teacher_subject row %s" % (pair,))
        seen_pairs.add(pair)
        skills[row["teacher_id"]].add(row["subject_id"])

    placeholder_ids = {s["subject_id"] for s in subjects if s["is_language_slot"]}
    check(not (placeholder_ids & {p[1] for p in seen_pairs}),
          "the Second Language placeholder must not be teachable")

    # --- 7. language groups ------------------------------------------------
    group_of_student = {}
    for group in language_groups:
        check(group["subject_id"] in subject_ids,
              "group %s points at an unknown subject" % group["language_group_id"])
        check(subjects_by_id[group["subject_id"]]["is_second_language"],
              "group %s teaches a subject that is not a second language"
              % group["language_group_id"])
        check(group["strength"] == len(group["student_ids"]),
              "group %s strength does not match its member list"
              % group["language_group_id"])
        check(group["strength"] == sum(group["class_distribution"].values()),
              "group %s strength does not match its class-wise counts"
              % group["language_group_id"])
        check(group["strength"] <= config["max_language_group_size"],
              "group %s is over the size limit" % group["language_group_id"])
        check(set(group["class_distribution"]) <= class_ids,
              "group %s lists an unknown class" % group["language_group_id"])

        per_class = defaultdict(int)
        for student_id in group["student_ids"]:
            student = student_by_id.get(student_id)
            check(student is not None,
                  "group %s lists an unknown student" % group["language_group_id"])
            check(student_id not in group_of_student,
                  "student %s is in more than one language group" % student_id)
            group_of_student[student_id] = group
            if student is not None:
                per_class[student["class_id"]] += 1

        check(dict(per_class) == group["class_distribution"],
              "group %s class-wise counts do not match its members"
              % group["language_group_id"])

    for student in students:
        group = group_of_student.get(student["student_id"])
        check(group is not None,
              "student %s is in no language group" % student["student_id"])
        if group is not None:
            check(group["language"] == student["second_language"],
                  "student %s is in a %s group but chose %s"
                  % (student["student_id"], group["language"],
                     student["second_language"]))

    # --- 8. teaching assignments -------------------------------------------
    load = defaultdict(int)
    covered_class_subjects = defaultdict(int)
    covered_groups = defaultdict(int)

    for assignment in assignments:
        teacher_id = assignment["teacher_id"]
        check(teacher_id in teacher_ids,
              "assignment %s has an unknown teacher" % assignment["assignment_id"])
        check(assignment["subject_id"] in subject_ids,
              "assignment %s has an unknown subject" % assignment["assignment_id"])
        check(assignment["subject_id"] in skills.get(teacher_id, set()),
              "assignment %s gives %s a subject they cannot teach"
              % (assignment["assignment_id"], teacher_id))
        check(assignment["weekly_periods"] > 0,
              "assignment %s has no periods" % assignment["assignment_id"])

        if assignment["target_type"] == "class":
            check(assignment["target_id"] in class_ids,
                  "assignment %s targets an unknown class"
                  % assignment["assignment_id"])
            covered_class_subjects[assignment["class_subject_id"]] += 1
        elif assignment["target_type"] == "language_group":
            check(assignment["target_id"] in group_ids,
                  "assignment %s targets an unknown language group"
                  % assignment["assignment_id"])
            covered_groups[assignment["target_id"]] += 1
        else:
            errors.append("assignment %s has an unknown target_type %r"
                          % (assignment["assignment_id"],
                             assignment["target_type"]))

        load[teacher_id] += assignment["weekly_periods"]

    # every class subject taught exactly once, with the right period count
    assignment_by_class_subject = {a["class_subject_id"]: a for a in assignments
                                   if a["target_type"] == "class"}
    for row in class_subjects:
        if row["taught_in_language_groups"]:
            continue        # covered through language groups instead
        count = covered_class_subjects[row["class_subject_id"]]
        check(count == 1,
              "class_subject %s has %d teachers, expected exactly 1"
              % (row["class_subject_id"], count))
        assignment = assignment_by_class_subject.get(row["class_subject_id"])
        if assignment:
            check(assignment["weekly_periods"] == row["weekly_periods"],
                  "assignment %s does not deliver the required periods"
                  % assignment["assignment_id"])
            check(assignment["subject_id"] == row["subject_id"],
                  "assignment %s teaches the wrong subject"
                  % assignment["assignment_id"])

    # every language group taught exactly once, for the class slot length
    for group in language_groups:
        count = covered_groups[group["language_group_id"]]
        check(count == 1,
              "language group %s has %d teachers, expected exactly 1"
              % (group["language_group_id"], count))
        for class_id in group["class_ids"]:
            check(slot_subject_periods.get(class_id) == group["weekly_periods"],
                  "group %s does not match the second-language slot of class %s"
                  % (group["language_group_id"], class_id))

    # --- 9. teacher workload ----------------------------------------------
    for teacher in teachers:
        assigned = load[teacher["teacher_id"]]
        check(assigned == teacher["assigned_weekly_periods"],
              "teacher %s has a stale assigned_weekly_periods"
              % teacher["teacher_id"])
        check(assigned <= teacher["max_weekly_periods"],
              "teacher %s is over their weekly maximum (%d > %d)"
              % (teacher["teacher_id"], assigned, teacher["max_weekly_periods"]))
        check(assigned <= teacher["available_period_count"],
              "teacher %s is assigned more periods than they are available for"
              % teacher["teacher_id"])

        available = sum(len(v) for v in teacher["availability"].values())
        check(available == teacher["available_period_count"],
              "teacher %s availability count is wrong" % teacher["teacher_id"])
        check(set(teacher["availability"]) == set(days),
              "teacher %s availability is missing a day" % teacher["teacher_id"])
        for day, day_periods in teacher["availability"].items():
            check(set(day_periods) <= set(periods),
                  "teacher %s is available in an unknown period on %s"
                  % (teacher["teacher_id"], day))

    # every teacher referenced as a class teacher must exist (checked above)
    check(all(t in teachers_by_id for t in class_teacher_ids),
          "a class teacher id is not a real teacher")

    return errors


# ===========================================================================
# 6. ENTRY POINT
# ===========================================================================

def write_json(dataset: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(dataset, handle, indent=2, ensure_ascii=False)


def print_report(dataset: dict) -> None:
    summary = dataset["summary"]
    structure = dataset["timetable_structure"]

    print("Synthetic timetable dataset - %s (seed %d)"
          % (dataset["academic_year"]["name"], dataset["meta"]["seed"]))
    print()
    print("  classes              : %d" % summary["classes"])
    print("  students             : %d" % summary["students"])
    print("  teachers             : %d" % summary["teachers"])
    print("  subjects             : %d" % summary["subjects"])
    print("  class-subject rows   : %d" % summary["class_subject_rows"])
    print("  teacher-subject rows : %d" % summary["teacher_subject_rows"])
    print("  language groups      : %d" % summary["language_groups"])
    print("  teaching assignments : %d" % summary["teaching_assignments"])
    print("  weekly slots / class : %d (%d days x %d periods, lunch after %s)"
          % (structure["total_weekly_slots"],
             len(structure["working_days"]),
             structure["periods_per_day"],
             structure["lunch_after_period"]))
    print("  teacher load         : min %d, avg %.1f, max %d"
          % (summary["teacher_load"]["min"],
             summary["teacher_load"]["average"],
             summary["teacher_load"]["max"]))
    print()

    print("Second-language uptake:")
    for language, count in summary["students_per_second_language"].items():
        print("  %-12s %4d students" % (language, count))
    print()

    print("Language groups:")
    for group in dataset["language_groups"]:
        spread = ", ".join(
            "%s:%d" % (class_id, count)
            for class_id, count in group["class_distribution"].items()
        )
        print("  %-6s %-18s strength %3d   from %s"
              % (group["language_group_id"], group["name"],
                 group["strength"], spread))
    print()

    print("Classes:")
    for klass in dataset["classes"]:
        print("  %-7s %-30s strength %3d   class teacher %s"
              % (klass["class_id"], klass["name"],
                 klass["student_strength"], klass["class_teacher_id"]))


def main() -> int:
    dataset = build_dataset(CONFIG)
    errors = validate_dataset(dataset)

    print_report(dataset)
    print()

    if errors:
        print("VALIDATION FAILED - %d problem(s):" % len(errors))
        for message in errors:
            print("  - %s" % message)
        return 1

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "synthetic_dataset.json")
    write_json(dataset, output_path)

    print("Validation passed: all references, counts and workloads are consistent.")
    print("Dataset written to %s" % output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
