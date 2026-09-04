"""
ga_v1.py
--------
V1 genetic algorithm timetable generator: many classes, many teachers,
shared second-language bands, 5 days x 7 periods, lunch between P4 and P5.

The GA core knows nothing about Laravel, FastAPI or a database. It works
on a TimetableProblem, which is built from a plain dict (see
timetable_problem.py). Feeding it an API response instead of a local file
changes only load_dataset() - never the algorithm.

Chromosome
    A list parallel to problem.units. Entry i holds the slot indexes for
    unit i, one per weekly period it needs. A unit is either a class lesson
    (one class, one teacher) or a second-language band (several groups and
    teachers running at the same time across several classes), so a
    chromosome is a complete timetable for every class at once.

Fitness
    fitness = soft score (0..100) - HARD_PENALTY x hard violations

    Hard and soft are always counted separately and reported separately.
    With HARD_PENALTY at 500, a single hard violation outweighs every soft
    point available, so the search fixes clashes before it polishes.

Run:  python ga_v1.py
      python ga_v1.py --generations 600 --population 80
      python ga_v1.py --dataset synthetic_dataset.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from collections import defaultdict, namedtuple

from timetable_problem import TimetableProblem

# ===========================================================================
# Configuration
# ===========================================================================

GA_CONFIG = {
    "seed": 7,
    "population_size": 60,
    "generations": 400,
    "elite_count": 3,
    "tournament_size": 4,
    "crossover_rate": 0.85,
    "mutation_rate": 0.35,        # chance a child is mutated at all
    "mutation_moves": 2,          # random operators applied when it is
    "repair_passes": 6,           # local-search repairs applied to each child
    "target_soft_score": 88.0,    # stop early once this is reached with 0 hard
    "stagnation_limit": 150,      # generations without improvement
}

# One hard violation must dominate the entire soft range (0..100).
HARD_PENALTY = 500.0

# Soft weights add up to 100, so the soft score reads as a percentage.
SOFT_WEIGHTS = {
    "period_priority": 30.0,
    "class_teacher_first_period": 10.0,
    "subject_distribution": 25.0,
    "teacher_workload": 15.0,
    "gaps_and_blocks": 20.0,
}

HARD_KEYS = (
    "class_clash",
    "teacher_clash",
    "required_periods",
    "duplicate_period",
    "teacher_eligibility",
    "teacher_availability",
    "language_band",
)

HARD_LABELS = {
    "class_clash": "class booked twice in one slot",
    "teacher_clash": "teacher booked twice in one slot",
    "required_periods": "wrong number of weekly periods",
    "duplicate_period": "same lesson twice in one slot",
    "teacher_eligibility": "teacher not qualified for the subject",
    "teacher_availability": "teacher scheduled when unavailable",
    "language_band": "invalid language-group scheduling",
}

SOFT_LABELS = {
    "period_priority": "high-load subjects in high-priority periods",
    "class_teacher_first_period": "class teacher takes P1 (preference only)",
    "subject_distribution": "subjects spread across the week",
    "teacher_workload": "teacher load balanced across days",
    "gaps_and_blocks": "no idle gaps or over-long subject blocks",
}

# The shipped generator config produces more language groups than there are
# language teachers, and every class must sit its second language in one
# parallel band - so those groups would all have to run at once. Raising the
# group cap yields one group per language, which is schedulable. This
# overrides CONFIG only; the generator itself is untouched.
DEMO_DATA_OVERRIDES = {"max_language_group_size": 250}

Evaluation = namedtuple(
    "Evaluation", "fitness hard hard_total soft soft_total"
)


# ===========================================================================
# Fitness
# ===========================================================================

def evaluate(problem: TimetableProblem, genes: list) -> Evaluation:
    """Score a chromosome, keeping hard and soft results separate."""
    n_slots = problem.n_slots
    n_days = len(problem.days)
    periods_per_day = problem.periods_per_day

    class_occupancy = [[0] * n_slots for _ in problem.classes]
    teacher_occupancy = [[0] * n_slots for _ in problem.teachers]
    class_subject_grid = [[None] * n_slots for _ in problem.classes]
    class_unit_grid = [[None] * n_slots for _ in problem.classes]

    hard = dict.fromkeys(HARD_KEYS, 0)
    hard["teacher_eligibility"] = len(problem.eligibility_violations)

    priority_raw = 0.0
    band_slots_per_class = defaultdict(set)

    for unit in problem.units:
        slots = genes[unit.index]

        if len(slots) != unit.periods:
            hard["required_periods"] += abs(len(slots) - unit.periods)

        seen = set()
        for slot in slots:
            if slot in seen:
                hard["duplicate_period"] += 1
            seen.add(slot)

            priority = problem.slot_priority[slot]
            for c in unit.class_indexes:
                class_occupancy[c][slot] += 1
                class_subject_grid[c][slot] = unit.subject_key
                class_unit_grid[c][slot] = unit.index
                priority_raw += unit.weight * priority
                if unit.kind == "band":
                    band_slots_per_class[c].add(slot)

            for t in unit.teacher_indexes:
                teacher_occupancy[t][slot] += 1
                if not problem.teacher_available[t][slot]:
                    hard["teacher_availability"] += 1

    for row in class_occupancy:
        for count in row:
            if count > 1:
                hard["class_clash"] += count - 1

    for row in teacher_occupancy:
        for count in row:
            if count > 1:
                hard["teacher_clash"] += count - 1

    # Language bands: every class must get exactly the second-language
    # periods it reserved, all of them inside its band.
    for c in range(len(problem.classes)):
        required = problem.class_band_periods[c]
        if required and len(band_slots_per_class[c]) != required:
            hard["language_band"] += abs(
                len(band_slots_per_class[c]) - required
            )

    hard_total = sum(hard.values())

    # ----------------------------------------------------------- soft ----
    soft = {}

    spread = problem.priority_best - problem.priority_worst
    soft["period_priority"] = (
        (priority_raw - problem.priority_worst) / spread if spread else 1.0
    )

    # class teacher opening the day - a preference, never a hard rule
    hits = 0
    for c in range(len(problem.classes)):
        teacher = problem.class_teacher_index[c]
        if teacher is None:
            continue
        for day in range(n_days):
            unit_index = class_unit_grid[c][day * periods_per_day]
            if unit_index is not None and teacher in problem.units[unit_index].teacher_indexes:
                hits += 1
    opportunities = sum(problem.class_teacher_opportunities)
    soft["class_teacher_first_period"] = hits / opportunities if opportunities else 1.0

    # subject spread: same subject twice a day, or long unbroken blocks
    repeat_penalty = 0
    for c in range(len(problem.classes)):
        grid = class_subject_grid[c]
        for day in range(n_days):
            start = day * periods_per_day
            day_subjects = grid[start:start + periods_per_day]

            counts = defaultdict(int)
            for subject in day_subjects:
                if subject is not None:
                    counts[subject] += 1
            repeat_penalty += sum(v - 1 for v in counts.values() if v > 1)

            run_subject, run_length = None, 0
            for subject in day_subjects:
                if subject is not None and subject == run_subject:
                    run_length += 1
                else:
                    if run_length > 2:
                        repeat_penalty += run_length - 2
                    run_subject, run_length = subject, 1
            if run_length > 2:
                repeat_penalty += run_length - 2

    soft["subject_distribution"] = 1.0 - min(
        1.0, repeat_penalty / problem.max_repeat_penalty
    )

    # teacher workload spread over the days, and idle gaps inside a day
    deviation_total = 0.0
    active_teachers = 0
    gap_penalty = 0

    for t in range(len(problem.teachers)):
        row = teacher_occupancy[t]
        load = sum(row)
        if not load:
            continue
        active_teachers += 1

        daily = []
        for day in range(n_days):
            start = day * periods_per_day
            day_slots = row[start:start + periods_per_day]
            daily.append(sum(day_slots))

            taught = [i for i, v in enumerate(day_slots) if v]
            if taught:
                gap_penalty += (taught[-1] - taught[0] + 1) - len(taught)

        ideal = load / n_days
        deviation_total += sum(abs(count - ideal) for count in daily) / (2 * load)

    soft["teacher_workload"] = (
        1.0 - deviation_total / active_teachers if active_teachers else 1.0
    )
    soft["gaps_and_blocks"] = 1.0 - min(1.0, gap_penalty / problem.max_gap_penalty)

    soft_total = sum(SOFT_WEIGHTS[key] * value for key, value in soft.items())
    fitness = soft_total - HARD_PENALTY * hard_total

    return Evaluation(fitness, hard, hard_total, soft, soft_total)


# ===========================================================================
# Occupancy helper, shared by the repair operators
# ===========================================================================

def occupancy(problem: TimetableProblem, genes: list) -> tuple:
    class_occupancy = [[0] * problem.n_slots for _ in problem.classes]
    teacher_occupancy = [[0] * problem.n_slots for _ in problem.teachers]

    for unit in problem.units:
        for slot in genes[unit.index]:
            for c in unit.class_indexes:
                class_occupancy[c][slot] += 1
            for t in unit.teacher_indexes:
                teacher_occupancy[t][slot] += 1

    return class_occupancy, teacher_occupancy


# ===========================================================================
# Population initialisation
#
# Random chromosomes are hopeless here: every class is nearly full, so a
# random draw produces hundreds of clashes. Instead each individual is
# built greedily - bands first, then every class filled slot by slot with a
# lesson whose teacher is free and available - which starts the GA close to
# feasible and lets it spend its time on repair and polish.
# ===========================================================================

def greedy_chromosome(problem: TimetableProblem, rng: random.Random,
                      allowed_sets: list) -> list:
    genes = [[] for _ in problem.units]
    class_busy = [[False] * problem.n_slots for _ in problem.classes]
    teacher_busy = [[False] * problem.n_slots for _ in problem.teachers]

    # --- bands first: they block the same slots in every member class ------
    for index in problem.band_unit_indexes:
        unit = problem.units[index]
        chosen = []
        days = list(range(len(problem.days)))
        rng.shuffle(days)

        # prefer one band period per day, so the band is spread out
        for day in days:
            if len(chosen) >= unit.periods:
                break
            options = [
                slot for slot in problem.slots_by_day[day]
                if slot in allowed_sets[index]
                and not any(class_busy[c][slot] for c in unit.class_indexes)
                and not any(teacher_busy[t][slot] for t in unit.teacher_indexes)
            ]
            if options:
                chosen.append(rng.choice(options))

        # top up if the per-day preference could not supply enough
        if len(chosen) < unit.periods:
            options = [s for s in unit.allowed_slots if s not in chosen]
            rng.shuffle(options)
            chosen.extend(options[:unit.periods - len(chosen)])

        genes[index] = chosen[:unit.periods]
        for slot in genes[index]:
            for c in unit.class_indexes:
                class_busy[c][slot] = True
            for t in unit.teacher_indexes:
                teacher_busy[t][slot] = True

    # --- then fill each class, slot by slot --------------------------------
    class_order = list(range(len(problem.classes)))
    rng.shuffle(class_order)

    for c in class_order:
        lessons = []
        for index in problem.class_unit_indexes[c]:
            lessons.extend([index] * problem.units[index].periods)
        rng.shuffle(lessons)

        free_slots = [s for s in range(problem.n_slots) if not class_busy[c][s]]
        rng.shuffle(free_slots)

        # bands are already placed, so the class starts the day with them
        subjects_on_day = defaultdict(set)
        for index in problem.band_unit_indexes:
            for slot in genes[index]:
                if c in problem.units[index].class_indexes:
                    subjects_on_day[problem.day_of(slot)].add("Second Language")

        for slot in free_slots:
            if not lessons:
                break

            day = problem.day_of(slot)
            fallback = None
            picked = None

            for position, index in enumerate(lessons):
                unit = problem.units[index]
                if slot not in allowed_sets[index]:
                    continue
                if any(teacher_busy[t][slot] for t in unit.teacher_indexes):
                    continue
                if slot in genes[index]:
                    continue
                if fallback is None:
                    fallback = position
                if unit.subject_key not in subjects_on_day[day]:
                    picked = position
                    break

            if picked is None:
                picked = fallback
            if picked is None:
                # Nothing fits without a clash. Prefer a lesson that at least
                # is not already in this slot and whose teacher may work then,
                # and leave the rest for the repair operator.
                for position, index in enumerate(lessons):
                    if slot in genes[index]:
                        continue
                    picked = position
                    if slot in allowed_sets[index]:
                        break
            if picked is None:
                picked = 0

            index = lessons.pop(picked)
            unit = problem.units[index]
            genes[index].append(slot)
            class_busy[c][slot] = True
            for t in unit.teacher_indexes:
                teacher_busy[t][slot] = True
            subjects_on_day[day].add(unit.subject_key)

        # any lesson still unplaced goes somewhere legal-ish
        for index in lessons:
            unit = problem.units[index]
            options = [s for s in unit.allowed_slots if s not in genes[index]]
            genes[index].append(
                rng.choice(options) if options
                else rng.randrange(problem.n_slots)
            )

    return genes


def initial_population(problem, rng, allowed_sets, size):
    return [greedy_chromosome(problem, rng, allowed_sets) for _ in range(size)]


# ===========================================================================
# Selection
# ===========================================================================

def tournament_selection(population, scores, rng, tournament_size):
    best = None
    for _ in range(tournament_size):
        index = rng.randrange(len(population))
        if best is None or scores[index] > scores[best]:
            best = index
    return population[best]


# ===========================================================================
# Crossover - class-wise
#
# Every class inherits all of its lessons from one parent, so a class that
# was internally clash-free in a parent stays clash-free in the child. Bands
# are global, so they come from the first parent as a block.
# ===========================================================================

def crossover(problem, parent_a, parent_b, rng):
    child = [None] * len(problem.units)

    for index in problem.band_unit_indexes:
        child[index] = list(parent_a[index])

    for unit_indexes in problem.class_unit_indexes:
        source = parent_a if rng.random() < 0.5 else parent_b
        for index in unit_indexes:
            child[index] = list(source[index])

    return child


# ===========================================================================
# Mutation and repair
# ===========================================================================

def move_lesson(problem, genes, rng, allowed_sets):
    """Move one lesson of a random class unit to another allowed slot."""
    candidates = [u.index for u in problem.units if u.kind == "class"]
    if not candidates:
        return
    index = rng.choice(candidates)
    unit = problem.units[index]
    if not genes[index] or not unit.allowed_slots:
        return

    position = rng.randrange(len(genes[index]))
    options = [s for s in unit.allowed_slots if s not in genes[index]]
    if options:
        genes[index][position] = rng.choice(options)


def swap_within_class(problem, genes, rng):
    """Swap the slots of two lessons of the same class.

    The class stays exactly as full as it was, which is what makes this the
    workhorse move on a timetable with no free periods.
    """
    c = rng.randrange(len(problem.classes))
    placements = []
    for index in problem.class_unit_indexes[c]:
        for position in range(len(genes[index])):
            placements.append((index, position))
    if len(placements) < 2:
        return

    (unit_a, pos_a), (unit_b, pos_b) = rng.sample(placements, 2)
    if unit_a == unit_b:
        return

    slot_a, slot_b = genes[unit_a][pos_a], genes[unit_b][pos_b]
    if slot_a == slot_b or slot_b in genes[unit_a] or slot_a in genes[unit_b]:
        return

    genes[unit_a][pos_a], genes[unit_b][pos_b] = slot_b, slot_a


def repair(problem, genes, rng, allowed_sets):
    """Fix one hard violation if a safe move or swap exists.

    Tries the cheap fix first (move the lesson to a slot nobody is using),
    then the swap that a full timetable actually needs.
    """
    class_occupancy, teacher_occupancy = occupancy(problem, genes)

    offenders = []
    for unit in problem.units:
        for position, slot in enumerate(genes[unit.index]):
            clash = (
                any(class_occupancy[c][slot] > 1 for c in unit.class_indexes)
                or any(teacher_occupancy[t][slot] > 1 for t in unit.teacher_indexes)
                or any(not problem.teacher_available[t][slot]
                       for t in unit.teacher_indexes)
            )
            if clash:
                offenders.append((unit.index, position, slot))

    if not offenders:
        return False

    index, position, slot = offenders[rng.randrange(len(offenders))]
    unit = problem.units[index]

    # 1) a slot that is completely free for every class and teacher involved
    free = [
        s for s in unit.allowed_slots
        if s not in genes[index]
        and all(class_occupancy[c][s] == 0 for c in unit.class_indexes)
        and all(teacher_occupancy[t][s] == 0 for t in unit.teacher_indexes)
    ]
    if free:
        genes[index][position] = rng.choice(free)
        return True

    # 2) swap with another lesson of the same class
    if unit.kind != "class":
        return False

    c = unit.class_indexes[0]
    partners = []
    for other in problem.class_unit_indexes[c]:
        if other == index:
            continue
        other_unit = problem.units[other]
        for other_position, other_slot in enumerate(genes[other]):
            if other_slot == slot:
                continue
            if other_slot not in allowed_sets[index]:
                continue
            if slot not in allowed_sets[other]:
                continue
            if other_slot in genes[index] or slot in genes[other]:
                continue

            # after the swap both teachers must land on an empty slot
            ok = True
            for t in unit.teacher_indexes:
                busy = teacher_occupancy[t][other_slot] - (
                    1 if t in other_unit.teacher_indexes else 0
                )
                if busy:
                    ok = False
                    break
            if ok:
                for t in other_unit.teacher_indexes:
                    busy = teacher_occupancy[t][slot] - (
                        1 if t in unit.teacher_indexes else 0
                    )
                    if busy:
                        ok = False
                        break
            if ok:
                partners.append((other, other_position, other_slot))

    if partners:
        other, other_position, other_slot = rng.choice(partners)
        genes[index][position] = other_slot
        genes[other][other_position] = slot
        return True

    # 3) hand the lesson an empty slot of its own class by displacing the one
    # lesson that blocks its teacher there. Swaps inside a class can never
    # fill an empty slot, so without this the search stalls one clash short.
    if cross_class_swap(problem, genes, rng, allowed_sets, class_occupancy,
                        teacher_occupancy, index, position, slot):
        return True

    # 4) otherwise take the best swap available, accepting it only if it
    # strictly reduces the problems around the two slots involved.
    return relaxed_swap(problem, genes, rng, allowed_sets, class_occupancy,
                        teacher_occupancy, index, position, slot)


def cross_class_swap(problem, genes, rng, allowed_sets, class_occupancy,
                     teacher_occupancy, index, position, slot,
                     sample_size: int = 25):
    """Move a lesson into a free slot of its class, displacing one blocker.

    The blocker is a lesson of another class taught by the same teacher; it
    takes over the slot being vacated, so both classes stay exactly as full
    as before.
    """
    unit = problem.units[index]
    if unit.kind != "class":
        return False

    c = unit.class_indexes[0]
    targets = [
        s for s in unit.allowed_slots
        if s not in genes[index] and class_occupancy[c][s] == 0
    ]
    if not targets:
        return False
    rng.shuffle(targets)

    for target in targets[:sample_size]:
        blockers = set()
        for t in unit.teacher_indexes:
            if not teacher_occupancy[t][target]:
                continue
            for other in problem.units_of_teacher[t]:
                if other != index and target in genes[other]:
                    blockers.add(other)

        if len(blockers) != 1:
            continue        # nobody to displace, or too tangled to be safe

        other = blockers.pop()
        other_unit = problem.units[other]
        if other_unit.kind != "class":
            continue
        if slot not in allowed_sets[other] or slot in genes[other]:
            continue
        if class_occupancy[other_unit.class_indexes[0]][slot]:
            continue

        # the displaced lesson must find the vacated slot free of its own
        # teachers, ignoring the teachers that are leaving it
        clear = True
        for t in other_unit.teacher_indexes:
            busy = teacher_occupancy[t][slot] - (
                1 if t in unit.teacher_indexes else 0
            )
            if busy:
                clear = False
                break
        if not clear:
            continue

        genes[index][position] = target
        genes[other][genes[other].index(target)] = slot
        return True

    return False


def placement_problems(problem, class_occupancy, teacher_occupancy, unit, slot):
    """How many things are wrong with this unit sitting in this slot.

    The unit is assumed to be counted in the occupancy arrays already.
    """
    problems = 0
    for c in unit.class_indexes:
        if class_occupancy[c][slot] > 1:
            problems += 1
    for t in unit.teacher_indexes:
        if teacher_occupancy[t][slot] > 1:
            problems += 1
        if not problem.teacher_available[t][slot]:
            problems += 1
    return problems


def relaxed_swap(problem, genes, rng, allowed_sets, class_occupancy,
                 teacher_occupancy, index, position, slot,
                 sample_size: int = 40):
    """Swap two lessons of one class if it leaves the pair better off."""
    unit = problem.units[index]
    c = unit.class_indexes[0]

    candidates = []
    for other in problem.class_unit_indexes[c]:
        if other == index:
            continue
        for other_position, other_slot in enumerate(genes[other]):
            if other_slot == slot:
                continue
            if other_slot in genes[index] or slot in genes[other]:
                continue
            candidates.append((other, other_position, other_slot))

    if not candidates:
        return False
    if len(candidates) > sample_size:
        candidates = rng.sample(candidates, sample_size)

    def move(unit_a, slot_from, slot_to):
        for t in unit_a.teacher_indexes:
            teacher_occupancy[t][slot_from] -= 1
            teacher_occupancy[t][slot_to] += 1

    for other, other_position, other_slot in candidates:
        other_unit = problem.units[other]

        before = (
            placement_problems(problem, class_occupancy, teacher_occupancy,
                               unit, slot)
            + placement_problems(problem, class_occupancy, teacher_occupancy,
                                 other_unit, other_slot)
        )

        move(unit, slot, other_slot)
        move(other_unit, other_slot, slot)
        after = (
            placement_problems(problem, class_occupancy, teacher_occupancy,
                               unit, other_slot)
            + placement_problems(problem, class_occupancy, teacher_occupancy,
                                 other_unit, slot)
        )
        move(unit, other_slot, slot)          # undo the trial
        move(other_unit, slot, other_slot)

        if after < before:
            genes[index][position] = other_slot
            genes[other][other_position] = slot
            return True

    return False


def mutate(problem, genes, rng, allowed_sets, config):
    for _ in range(config["mutation_moves"]):
        if rng.random() < 0.5:
            swap_within_class(problem, genes, rng)
        else:
            move_lesson(problem, genes, rng, allowed_sets)


# ===========================================================================
# Evolution
# ===========================================================================

def evolve(problem: TimetableProblem, config: dict = GA_CONFIG,
           verbose: bool = True) -> tuple:
    """Run the GA. Returns (best_genes, best_evaluation, history)."""
    rng = random.Random(config["seed"])
    allowed_sets = [set(unit.allowed_slots) for unit in problem.units]

    population = initial_population(
        problem, rng, allowed_sets, config["population_size"]
    )
    evaluations = [evaluate(problem, genes) for genes in population]
    scores = [e.fitness for e in evaluations]

    best_index = max(range(len(population)), key=lambda i: scores[i])
    best_genes = [list(slots) for slots in population[best_index]]
    best_evaluation = evaluations[best_index]

    history = []
    stagnant = 0

    for generation in range(1, config["generations"] + 1):
        ranked = sorted(range(len(population)), key=lambda i: scores[i], reverse=True)
        new_population = [
            [list(slots) for slots in population[i]]
            for i in ranked[:config["elite_count"]]
        ]

        while len(new_population) < config["population_size"]:
            parent_a = tournament_selection(population, scores, rng,
                                            config["tournament_size"])
            if rng.random() < config["crossover_rate"]:
                parent_b = tournament_selection(population, scores, rng,
                                                config["tournament_size"])
                child = crossover(problem, parent_a, parent_b, rng)
            else:
                child = [list(slots) for slots in parent_a]

            if rng.random() < config["mutation_rate"]:
                mutate(problem, child, rng, allowed_sets, config)

            # local search: hard violations get repaired before scoring
            for _ in range(config["repair_passes"]):
                if not repair(problem, child, rng, allowed_sets):
                    break

            new_population.append(child)

        population = new_population
        evaluations = [evaluate(problem, genes) for genes in population]
        scores = [e.fitness for e in evaluations]

        generation_best = max(range(len(population)), key=lambda i: scores[i])
        if scores[generation_best] > best_evaluation.fitness:
            best_evaluation = evaluations[generation_best]
            best_genes = [list(slots) for slots in population[generation_best]]
            stagnant = 0
        else:
            stagnant += 1

        history.append({
            "generation": generation,
            "best_fitness": best_evaluation.fitness,
            "hard_violations": best_evaluation.hard_total,
            "soft_score": best_evaluation.soft_total,
        })

        if verbose and (generation == 1 or generation % 25 == 0):
            print("  gen %4d   fitness %9.2f   hard %3d   soft %6.2f"
                  % (generation, best_evaluation.fitness,
                     best_evaluation.hard_total, best_evaluation.soft_total))

        # --- termination ---------------------------------------------------
        if (best_evaluation.hard_total == 0
                and best_evaluation.soft_total >= config["target_soft_score"]):
            if verbose:
                print("  stopping: no hard violations and soft target reached")
            break

        if stagnant >= config["stagnation_limit"]:
            if verbose:
                print("  stopping: no improvement for %d generations" % stagnant)
            break

    return best_genes, best_evaluation, history


# ===========================================================================
# Reporting
# ===========================================================================

def build_grids(problem: TimetableProblem, genes: list) -> tuple:
    """(class_grid, teacher_grid) with one cell per slot."""
    class_grid = [[[] for _ in range(problem.n_slots)] for _ in problem.classes]
    teacher_grid = [[[] for _ in range(problem.n_slots)] for _ in problem.teachers]

    for unit in problem.units:
        for slot in genes[unit.index]:
            for c in unit.class_indexes:
                class_grid[c][slot].append(unit)
            for t in unit.teacher_indexes:
                teacher_grid[t][slot].append(unit)

    return class_grid, teacher_grid


def print_validation_report(problem, evaluation: Evaluation) -> None:
    print("Hard constraints (must be zero)")
    for key in HARD_KEYS:
        count = evaluation.hard[key]
        mark = "ok  " if count == 0 else "FAIL"
        print("  [%s] %-34s %4d   %s"
              % (mark, key, count, HARD_LABELS[key]))
    print("  %-41s %4d" % ("total hard violations", evaluation.hard_total))
    print()

    print("Soft constraints (0.00 = worst, 1.00 = best)")
    for key, weight in SOFT_WEIGHTS.items():
        score = evaluation.soft[key]
        print("  %-30s %5.2f  x weight %5.1f = %6.2f   %s"
              % (key, score, weight, score * weight, SOFT_LABELS[key]))
    print("  %-30s %28.2f / %.0f"
          % ("soft score", evaluation.soft_total, sum(SOFT_WEIGHTS.values())))
    print()
    print("  fitness = soft %.2f - %.0f x %d hard = %.2f"
          % (evaluation.soft_total, HARD_PENALTY, evaluation.hard_total,
             evaluation.fitness))


def abbreviate(name: str, limit: int = 12) -> str:
    """Shorten a subject name for the printed grids, e.g. Computer Science."""
    if len(name) <= limit:
        return name
    words = name.split()
    if len(words) >= 2:
        short = "".join(word[:4] if i == 0 else word[:3]
                        for i, word in enumerate(words))
        if len(short) <= limit:
            return short
    return name[:limit]


def cell_text(problem, units, width, teacher_index=None):
    """One printed cell. With teacher_index set, show that teacher's own work."""
    if not units:
        return "-".ljust(width)

    parts = []
    for unit in units:
        if teacher_index is not None:
            # a band holds several groups; show only this teacher's group
            for member in unit.members:
                if problem.teacher_index[member["teacher_id"]] != teacher_index:
                    continue
                target = member["group_id"] or member["target_id"]
                parts.append("%s %s" % (target, abbreviate(member["subject"])))
        elif unit.kind == "band":
            parts.append("2nd Lang")
        else:
            teacher = problem.teacher_ids[unit.teacher_indexes[0]]
            parts.append("%s %s" % (abbreviate(unit.subject_key),
                                    teacher.replace("TCH-", "T")))

    text = " + ".join(parts)
    if len(text) >= width:
        text = text[:width - 1]
    return text.ljust(width)


def print_class_timetables(problem, genes) -> None:
    class_grid, _ = build_grids(problem, genes)
    width = 16
    lunch_index = problem.periods.index(problem.lunch_after_period)

    for c, klass in enumerate(problem.classes):
        teacher_id = problem.teacher_ids[problem.class_teacher_index[c]] \
            if problem.class_teacher_index[c] is not None else "-"
        print("%s  (%s)   class teacher %s"
              % (klass["name"], klass["class_id"], teacher_id))

        header = "  %-10s" % "Day"
        for index, period in enumerate(problem.periods):
            header += period.ljust(width)
            if index == lunch_index:
                header += "%-7s" % "LUNCH"
        print(header)

        for day_index, day in enumerate(problem.days):
            row = "  %-10s" % day
            for index in range(problem.periods_per_day):
                slot = day_index * problem.periods_per_day + index
                row += cell_text(problem, class_grid[c][slot], width)
                if index == lunch_index:
                    row += "%-7s" % "-----"
            print(row)
        print()


def print_teacher_timetables(problem, genes) -> None:
    _, teacher_grid = build_grids(problem, genes)
    width = 17
    lunch_index = problem.periods.index(problem.lunch_after_period)

    for t, teacher in enumerate(problem.teachers):
        load = sum(len(cell) for cell in teacher_grid[t])
        if not load:
            continue

        print("%s  %s   %s   %d/%d periods"
              % (teacher["teacher_id"], teacher["name"], teacher["department"],
                 load, teacher["max_weekly_periods"]))

        header = "  %-10s" % "Day"
        for index, period in enumerate(problem.periods):
            header += period.ljust(width)
            if index == lunch_index:
                header += "%-7s" % "LUNCH"
        print(header)

        for day_index, day in enumerate(problem.days):
            row = "  %-10s" % day
            for index in range(problem.periods_per_day):
                slot = day_index * problem.periods_per_day + index
                row += cell_text(problem, teacher_grid[t][slot], width,
                                 teacher_index=t)
                if index == lunch_index:
                    row += "%-7s" % "-----"
            print(row)
        print()


def solution_to_dict(problem, genes, evaluation: Evaluation) -> dict:
    """Serialisable timetable, class-wise and teacher-wise."""
    class_grid, teacher_grid = build_grids(problem, genes)

    def entry(unit, teacher_id=None):
        """One booked slot. For a teacher, narrowed to their own group."""
        members = list(unit.members)
        if teacher_id is not None:
            members = [m for m in members if m["teacher_id"] == teacher_id]

        return {
            "unit_id": unit.unit_id,
            "kind": unit.kind,
            "subject": (members[0]["subject"] if len(members) == 1
                        else unit.subject_key),
            "teachers": [problem.teacher_ids[t] for t in unit.teacher_indexes],
            "classes": [problem.class_ids[c] for c in unit.class_indexes],
            "groups": list(unit.group_ids),
            "assignments": list(unit.assignment_ids),
            # per-group detail: who teaches which language to which group
            "members": members,
        }

    classes = {}
    for c, klass in enumerate(problem.classes):
        grid = defaultdict(dict)
        for slot in range(problem.n_slots):
            day, period = problem.slots[slot]
            grid[day][period] = [entry(u) for u in class_grid[c][slot]]
        classes[klass["class_id"]] = {
            "name": klass["name"],
            "class_teacher_id": klass.get("class_teacher_id"),
            # what the class was owed, so a viewer can check it got it
            "requirements": problem.class_subject_requirements[c],
            "timetable": dict(grid),
        }

    teachers = {}
    for t, teacher in enumerate(problem.teachers):
        grid = defaultdict(dict)
        for slot in range(problem.n_slots):
            day, period = problem.slots[slot]
            grid[day][period] = [
                entry(u, teacher_id=teacher["teacher_id"])
                for u in teacher_grid[t][slot]
            ]
        teachers[teacher["teacher_id"]] = {
            "name": teacher["name"],
            "department": teacher["department"],
            "assigned_periods": sum(len(cell) for cell in teacher_grid[t]),
            "max_weekly_periods": teacher["max_weekly_periods"],
            # when this teacher may work, so availability clashes are
            # checkable from the solution file alone
            "availability": teacher["availability"],
            "timetable": dict(grid),
        }

    return {
        "structure": {
            "days": problem.days,
            "periods": problem.periods,
            "lunch_after_period": problem.lunch_after_period,
            "lunch_is_a_period": False,
        },
        "report": {
            "fitness": evaluation.fitness,
            "hard_violations": evaluation.hard,
            "hard_total": evaluation.hard_total,
            "soft_scores": evaluation.soft,
            "soft_weights": SOFT_WEIGHTS,
            "soft_total": evaluation.soft_total,
            "hard_penalty": HARD_PENALTY,
        },
        "classes": classes,
        "teachers": teachers,
    }


# ===========================================================================
# Data loading - the only place that touches the outside world
# ===========================================================================

def load_dataset(path: str | None = None) -> tuple:
    """Return (dataset, description).

    Swap this for an HTTP call and the GA core is unaffected:

        dataset = requests.get(f"{base}/api/timetable/dataset").json()
    """
    if path:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle), "file %s" % path

    # Local convenience only: build a dataset with the sibling generator.
    # Imported lazily so the GA never depends on it.
    from synthetic_data import CONFIG, build_dataset

    config = dict(CONFIG)
    config.update(DEMO_DATA_OVERRIDES)
    return (
        build_dataset(config),
        "synthetic_data.build_dataset() with overrides %s" % DEMO_DATA_OVERRIDES,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="V1 GA timetable generator")
    parser.add_argument("--dataset", help="dataset JSON file (default: generate)")
    parser.add_argument("--generations", type=int,
                        default=GA_CONFIG["generations"])
    parser.add_argument("--population", type=int,
                        default=GA_CONFIG["population_size"])
    parser.add_argument("--seed", type=int, default=GA_CONFIG["seed"])
    parser.add_argument("--target-soft", type=float,
                        default=GA_CONFIG["target_soft_score"])
    parser.add_argument("--output", default="timetable_solution.json")
    parser.add_argument("--no-teacher-view", action="store_true",
                        help="skip the teacher-wise timetables")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    dataset, source = load_dataset(args.dataset)
    problem = TimetableProblem.from_dataset(dataset)

    config = dict(GA_CONFIG)
    config.update({
        "generations": args.generations,
        "population_size": args.population,
        "seed": args.seed,
        "target_soft_score": args.target_soft,
    })

    print("V1 genetic algorithm timetable generator")
    print("  data source : %s" % source)
    print("  problem     : %s" % problem.describe())
    print("  ga          : population %d, up to %d generations, seed %d"
          % (config["population_size"], config["generations"], config["seed"]))
    print()

    issues = problem.feasibility_issues()
    if issues:
        print("This dataset cannot be scheduled - no timetable exists for it:")
        for issue in issues:
            print("  - %s" % issue)
        print()
        print("Fix the data (staffing, availability or period requirements) "
              "and run again.")
        return 2

    print("Evolving:")
    started = time.time()
    genes, evaluation, _history = evolve(problem, config)
    elapsed = time.time() - started
    print("  finished in %.1fs" % elapsed)
    print()

    print("=" * 78)
    print("VALIDATION REPORT")
    print("=" * 78)
    print_validation_report(problem, evaluation)
    print()

    print("=" * 78)
    print("CLASS-WISE TIMETABLES")
    print("=" * 78)
    print_class_timetables(problem, genes)

    if not args.no_teacher_view:
        print("=" * 78)
        print("TEACHER-WISE TIMETABLES")
        print("=" * 78)
        print_teacher_timetables(problem, genes)

    solution = solution_to_dict(problem, genes, evaluation)
    output_path = os.path.abspath(args.output)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(solution, handle, indent=2, ensure_ascii=False)
    print("Solution written to %s" % output_path)

    return 0 if evaluation.hard_total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
