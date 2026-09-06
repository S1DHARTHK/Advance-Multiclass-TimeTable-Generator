"""
slot_editor.py
--------------
"Move this lesson somewhere better" for an already generated timetable.

Given one booked slot, it finds the alternatives, checks each against every
hard constraint, scores the soft impact, and returns the best few - without
changing anything until the caller applies a choice.

No second rule system
---------------------
Every candidate is judged by rebuilding the chromosome with the change and
running ga_v1.evaluate() on it, exactly as the GA does. So "is this legal"
and "is this better" come from the same constraint and fitness code the
timetable was generated with. Add a constraint there and this feature
honours it automatically.

Two kinds of change:

    move   the lesson goes to a slot where its class is free
    swap   the lesson trades slots with another lesson of the same class

On a timetable where every class is already full, only swaps are possible;
moves matter as soon as a class has a free period.

Run:  python slot_editor.py --teacher TCH-04 --day Monday --period P1
"""

from __future__ import annotations

import argparse
import json
import os
from collections import namedtuple

from ga_v1 import (
    HARD_KEYS,
    HARD_LABELS,
    SOFT_WEIGHTS,
    evaluate,
    load_dataset,
    solution_to_dict,
)
from timetable_problem import TimetableProblem

# How many ranked alternatives to return by default.
DEFAULT_LIMIT = 5

Placement = namedtuple("Placement", "unit_index gene_position slot")


# ===========================================================================
# Helpers
# ===========================================================================

def slot_index(problem: TimetableProblem, day: str, period: str) -> int:
    return problem.days.index(day) * problem.periods_per_day + problem.periods.index(period)


def slot_name(problem: TimetableProblem, slot: int) -> dict:
    day, period = problem.slots[slot]
    return {"day": day, "period": period}


def genes_from_solution(problem: TimetableProblem, solution: dict) -> list:
    """Rebuild a chromosome from a saved solution file.

    Lets the editor pick up the timetable the GA already produced instead of
    re-running the search.
    """
    genes = [[] for _ in problem.units]
    unit_by_id = {unit.unit_id: unit for unit in problem.units}
    seen = {unit.unit_id: set() for unit in problem.units}

    for klass in solution.get("classes", {}).values():
        for day, periods in klass.get("timetable", {}).items():
            for period, entries in periods.items():
                for entry in entries:
                    unit = unit_by_id.get(entry["unit_id"])
                    if unit is None:
                        continue
                    slot = slot_index(problem, day, period)
                    # a band shows up in every member class; count it once
                    if slot in seen[unit.unit_id]:
                        continue
                    seen[unit.unit_id].add(slot)
                    genes[unit.index].append(slot)

    for unit in problem.units:
        genes[unit.index].sort()

    return genes


# ===========================================================================
# The editor
# ===========================================================================

class SlotEditor:
    """Suggests, previews and applies single-lesson changes."""

    def __init__(self, problem: TimetableProblem, genes: list):
        self.problem = problem
        self.genes = [list(slots) for slots in genes]
        self.baseline = evaluate(problem, self.genes)

    def set_genes(self, genes: list) -> None:
        """Replace the whole timetable, e.g. when restoring a version."""
        self.genes = [list(slots) for slots in genes]
        self.baseline = evaluate(self.problem, self.genes)

    # ------------------------------------------------------------- lookup

    def placements_at(self, teacher_id: str, day: str, period: str) -> list:
        """Every lesson this teacher has in that slot (usually exactly one)."""
        teacher = self.problem.teacher_index.get(teacher_id)
        if teacher is None:
            return []

        slot = slot_index(self.problem, day, period)
        found = []
        for unit in self.problem.units:
            if teacher not in unit.teacher_indexes:
                continue
            for position, booked in enumerate(self.genes[unit.index]):
                if booked == slot:
                    found.append(Placement(unit.index, position, slot))
        return found

    def describe_placement(self, placement: Placement,
                           teacher_id: str | None = None) -> dict:
        unit = self.problem.units[placement.unit_index]

        subject = unit.subject_key
        target = ", ".join(self.problem.class_ids[c] for c in unit.class_indexes)
        if teacher_id:
            # inside a band a teacher takes their own group, not the whole thing
            for member in unit.members:
                if member["teacher_id"] == teacher_id:
                    subject = member["subject"]
                    target = member["group_id"] or member["target_id"]
                    break

        return {
            "unit_id": unit.unit_id,
            "kind": unit.kind,
            "subject": subject,
            "target": target,
            "teachers": [self.problem.teacher_ids[t] for t in unit.teacher_indexes],
            "weekly_periods": unit.periods,
            **slot_name(self.problem, placement.slot),
        }

    # ------------------------------------------------- candidate building

    def _occupants(self, class_indexes, slot: int, exclude: int) -> list:
        """Units holding any of these classes at this slot."""
        found = []
        for unit in self.problem.units:
            if unit.index == exclude:
                continue
            if slot in self.genes[unit.index] and any(
                c in unit.class_indexes for c in class_indexes
            ):
                found.append(unit)
        return found

    def _apply_to(self, genes: list, change: dict) -> list:
        """Return a copy of genes with the change applied."""
        updated = [list(slots) for slots in genes]
        updated[change["unit_index"]][change["gene_position"]] = change["to_slot"]

        if change["kind"] == "swap":
            updated[change["partner_unit_index"]][change["partner_position"]] = (
                change["from_slot"]
            )
        return updated

    def _score(self, change: dict) -> dict:
        """Run the real fitness function over the changed timetable."""
        after = evaluate(self.problem, self._apply_to(self.genes, change))
        base = self.baseline

        broken = {
            key: after.hard[key] - base.hard[key]
            for key in HARD_KEYS
            if after.hard[key] > base.hard[key]
        }

        return {
            "valid": after.hard_total <= base.hard_total and not broken,
            "hard_total": after.hard_total,
            "hard_before": base.hard_total,
            "breaks": [
                {"constraint": key, "label": HARD_LABELS[key], "added": count}
                for key, count in broken.items()
            ],
            "soft_before": base.soft_total,
            "soft_after": after.soft_total,
            "soft_delta": after.soft_total - base.soft_total,
            "fitness_delta": after.fitness - base.fitness,
            "components": {
                key: {
                    "before": base.soft[key],
                    "after": after.soft[key],
                    "delta": after.soft[key] - base.soft[key],
                    "weight": SOFT_WEIGHTS[key],
                }
                for key in SOFT_WEIGHTS
            },
        }

    def candidates(self, placement: Placement, limit: int = DEFAULT_LIMIT,
                   teacher_id: str | None = None) -> dict:
        """Rank the alternatives for one booked lesson.

        Every slot in the week is tried as a move or a swap, checked against
        the full hard-constraint set, and scored with the same soft weights
        the GA optimised.
        """
        unit = self.problem.units[placement.unit_index]
        options = []
        rejected = 0

        for target in range(self.problem.n_slots):
            if target == placement.slot:
                continue

            occupants = self._occupants(unit.class_indexes, target,
                                        placement.unit_index)

            if not occupants:
                change = {
                    "kind": "move",
                    "unit_index": unit.index,
                    "gene_position": placement.gene_position,
                    "from_slot": placement.slot,
                    "to_slot": target,
                }
            elif len(occupants) == 1 and occupants[0].kind == "class" and unit.kind == "class":
                partner = occupants[0]
                # the partner must be free to take the vacated slot
                positions = [
                    i for i, booked in enumerate(self.genes[partner.index])
                    if booked == target
                ]
                if not positions:
                    continue
                change = {
                    "kind": "swap",
                    "unit_index": unit.index,
                    "gene_position": placement.gene_position,
                    "from_slot": placement.slot,
                    "to_slot": target,
                    "partner_unit_index": partner.index,
                    "partner_position": positions[0],
                }
            else:
                # several lessons, or a language band: swapping those would
                # move other classes too, so it is not offered here
                rejected += 1
                continue

            score = self._score(change)
            if not score["valid"]:
                rejected += 1
                continue

            options.append(self._present(change, score, teacher_id))

        options.sort(key=lambda item: item["fitness_delta"], reverse=True)

        return {
            "current": self.describe_placement(placement, teacher_id),
            "baseline": {
                "hard_total": self.baseline.hard_total,
                "soft_total": self.baseline.soft_total,
                "fitness": self.baseline.fitness,
            },
            "candidates": options[:limit],
            "considered": self.problem.n_slots - 1,
            "rejected": rejected,
        }

    def _present(self, change: dict, score: dict,
                 teacher_id: str | None = None) -> dict:
        """Turn an internal change into the payload the UI shows."""
        unit = self.problem.units[change["unit_index"]]
        payload = {
            # everything needed to replay this exact change on apply
            "change": {
                "kind": change["kind"],
                "unit_id": unit.unit_id,
                "from": slot_name(self.problem, change["from_slot"]),
                "to": slot_name(self.problem, change["to_slot"]),
                "partner_unit_id": (
                    self.problem.units[change["partner_unit_index"]].unit_id
                    if change["kind"] == "swap" else None
                ),
            },
            # the lesson being moved, so callers can label the change
            "lesson": {
                "unit_id": unit.unit_id,
                "subject": unit.subject_key,
                "target": ", ".join(
                    self.problem.class_ids[c] for c in unit.class_indexes
                ),
            },
            "kind": change["kind"],
            **slot_name(self.problem, change["to_slot"]),
            "valid": score["valid"],
            "hard_total": score["hard_total"],
            "breaks": score["breaks"],
            "soft_delta": round(score["soft_delta"], 3),
            "soft_after": round(score["soft_after"], 2),
            "fitness_delta": round(score["fitness_delta"], 3),
            "components": {
                key: round(value["delta"], 4)
                for key, value in score["components"].items()
            },
            "summary": self._summarise(change, score),
        }

        if change["kind"] == "swap":
            partner = self.problem.units[change["partner_unit_index"]]
            payload["partner"] = {
                "unit_id": partner.unit_id,
                "subject": partner.subject_key,
                "target": ", ".join(
                    self.problem.class_ids[c] for c in partner.class_indexes
                ),
                "moves_to": slot_name(self.problem, change["from_slot"]),
            }

        return payload

    def _summarise(self, change: dict, score: dict) -> str:
        delta = score["soft_delta"]
        if abs(delta) < 0.005:
            quality = "no measurable change in quality"
        elif delta > 0:
            quality = "improves the timetable by %.2f points" % delta
        else:
            quality = "costs %.2f points" % abs(delta)

        if change["kind"] == "swap":
            partner = self.problem.units[change["partner_unit_index"]]
            where = slot_name(self.problem, change["from_slot"])
            return "Swap with %s, which moves to %s %s - %s" % (
                partner.subject_key, where["day"], where["period"], quality
            )

        return "Move into a free period - %s" % quality

    # -------------------------------------------------- preview and apply

    def resolve(self, change_payload: dict) -> dict:
        """Turn the UI's change description back into an internal change."""
        unit_by_id = {unit.unit_id: unit for unit in self.problem.units}

        unit = unit_by_id.get(change_payload["unit_id"])
        if unit is None:
            raise ValueError("unknown unit %r" % change_payload.get("unit_id"))

        from_slot = slot_index(self.problem, change_payload["from"]["day"],
                               change_payload["from"]["period"])
        to_slot = slot_index(self.problem, change_payload["to"]["day"],
                             change_payload["to"]["period"])

        if from_slot not in self.genes[unit.index]:
            raise ValueError(
                "%s is no longer scheduled at %s %s"
                % (unit.unit_id, change_payload["from"]["day"],
                   change_payload["from"]["period"])
            )

        change = {
            "kind": change_payload["kind"],
            "unit_index": unit.index,
            "gene_position": self.genes[unit.index].index(from_slot),
            "from_slot": from_slot,
            "to_slot": to_slot,
        }

        if change_payload["kind"] == "swap":
            partner = unit_by_id.get(change_payload.get("partner_unit_id"))
            if partner is None:
                raise ValueError("swap needs a valid partner_unit_id")
            if to_slot not in self.genes[partner.index]:
                raise ValueError(
                    "%s is no longer scheduled at %s %s"
                    % (partner.unit_id, change_payload["to"]["day"],
                       change_payload["to"]["period"])
                )
            change["partner_unit_index"] = partner.index
            change["partner_position"] = self.genes[partner.index].index(to_slot)

        return change

    def preview(self, change_payload: dict) -> dict:
        """Score a change without touching the timetable."""
        change = self.resolve(change_payload)
        score = self._score(change)
        return self._present(change, score)

    def apply(self, change_payload: dict) -> dict:
        """Commit a change. Refuses anything that breaks a hard constraint."""
        change = self.resolve(change_payload)
        score = self._score(change)

        if not score["valid"]:
            raise ValueError(
                "refused: this change would break %s"
                % ", ".join(item["label"] for item in score["breaks"])
            )

        self.genes = self._apply_to(self.genes, change)
        self.baseline = evaluate(self.problem, self.genes)
        return self._present(change, score)

    # -------------------------------------------------------------- output

    def solution(self) -> dict:
        return solution_to_dict(self.problem, self.genes, self.baseline)


# ===========================================================================
# Loading
# ===========================================================================

def load_editor(dataset_path: str | None = None,
                solution_path: str | None = None) -> SlotEditor:
    """Build the problem and pick up the timetable the GA already produced."""
    dataset, _source = load_dataset(dataset_path)
    problem = TimetableProblem.from_dataset(dataset)

    solution_path = solution_path or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "timetable_solution.json"
    )
    if not os.path.exists(solution_path):
        raise SystemExit(
            "No timetable found at %s - run 'python ga_v1.py' first."
            % solution_path
        )

    with open(solution_path, encoding="utf-8") as handle:
        solution = json.load(handle)

    genes = genes_from_solution(problem, solution)

    missing = [
        unit.unit_id for unit in problem.units
        if len(genes[unit.index]) != unit.periods
    ]
    if missing:
        raise SystemExit(
            "The saved timetable does not match this dataset (%d units differ, "
            "e.g. %s). Re-run 'python ga_v1.py'."
            % (len(missing), ", ".join(missing[:3]))
        )

    return SlotEditor(problem, genes)


# ===========================================================================
# CLI - handy for checking the engine without the UI
# ===========================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="Alternative slots for one lesson")
    parser.add_argument("--teacher", required=True, help="e.g. TCH-04")
    parser.add_argument("--day", required=True)
    parser.add_argument("--period", required=True)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()

    editor = load_editor()
    placements = editor.placements_at(args.teacher, args.day, args.period)
    if not placements:
        print("%s teaches nothing at %s %s" % (args.teacher, args.day, args.period))
        return 1

    result = editor.candidates(placements[0], args.limit, args.teacher)
    current = result["current"]

    print("Current: %s for %s at %s %s"
          % (current["subject"], current["target"], current["day"], current["period"]))
    print("Timetable now: %d hard violations, soft %.2f"
          % (result["baseline"]["hard_total"], result["baseline"]["soft_total"]))
    print("Checked %d slots, %d rejected, %d valid alternatives"
          % (result["considered"], result["rejected"], len(result["candidates"])))
    print()

    for rank, option in enumerate(result["candidates"], 1):
        print("%d. %s %-3s  %-4s  soft %+.2f -> %.2f  | %s"
              % (rank, option["day"], option["period"], option["kind"],
                 option["soft_delta"], option["soft_after"], option["summary"]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
