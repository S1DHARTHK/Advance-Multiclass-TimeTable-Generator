/**
 * Hard-constraint checking, done on the timetable the UI is about to draw.
 *
 * This deliberately re-derives the violations from the schedule itself
 * rather than trusting the counts the generator reported: if the file is
 * stale, hand-edited, or produced by a different solver, the screen still
 * tells the truth.
 *
 * Soft scores are never mixed in here. They describe quality, not validity,
 * and are read straight from the report.
 */

export const VIOLATION_LABELS = {
  class_clash: "Class clash",
  teacher_clash: "Teacher clash",
  availability_clash: "Availability clash",
  period_mismatch: "Wrong number of periods",
};

export const VIOLATION_HINTS = {
  class_clash: "a class is booked for two lessons in the same period",
  teacher_clash: "a teacher is booked in two places in the same period",
  availability_clash: "a teacher is scheduled when they are not available",
  period_mismatch: "a subject did not get its required weekly periods",
};

const slotKey = (day, period) => `${day}|${period}`;

function addCellConflict(map, id, day, period, violation) {
  if (!map[id]) map[id] = {};
  if (!map[id][day]) map[id][day] = {};
  if (!map[id][day][period]) map[id][day][period] = [];
  map[id][day][period].push(violation);
}

export function validateSolution(solution) {
  const { days, periods, classes } = solution;

  const violations = [];
  const classCells = {};    // classId -> day -> period -> [violation]
  const teacherCells = {};  // teacherId -> day -> period -> [violation]

  // teacherId -> slot -> Map(unitId -> what they are doing)
  const teacherSlots = {};
  // unitId|slot -> [classId], so a teacher problem can highlight class cells
  const classesOfUnitSlot = {};

  classes.forEach((klass) => {
    days.forEach((day) => {
      periods.forEach((period) => {
        const entries = klass.grid[day]?.[period] ?? [];

        // --- class clash: two different lessons in one class period ------
        const unitIds = [...new Set(entries.map((entry) => entry.unitId))];
        if (unitIds.length > 1) {
          const violation = {
            type: "class_clash",
            scope: "class",
            id: klass.id,
            day,
            period,
            message: `${klass.name} is booked for ${unitIds.length} lessons at ${day} ${period}: ${entries
              .map((entry) => entry.subject)
              .join(", ")}`,
          };
          violations.push(violation);
          addCellConflict(classCells, klass.id, day, period, violation);
        }

        entries.forEach((entry) => {
          const key = `${entry.unitId}|${slotKey(day, period)}`;
          (classesOfUnitSlot[key] ??= []).push(klass.id);

          entry.teachers.forEach((teacher) => {
            // a teacher's own subject inside a band is their group's language
            const member = entry.members.find(
              (item) => item.teacherId === teacher.id
            );
            // the id keeps two look-alike lessons of one class distinct
            const what =
              entry.kind === "band"
                ? `${member?.groupId ?? "language group"} ${member?.subject ?? entry.subject} (${entry.unitId})`
                : `${klass.id} ${entry.subject} (${entry.unitId})`;

            ((teacherSlots[teacher.id] ??= {})[slotKey(day, period)] ??=
              new Map()).set(entry.unitId, { what, name: teacher.name });
          });
        });
      });
    });
  });

  // --- teacher clashes and availability --------------------------------
  Object.entries(solution.teachers).forEach(([teacherId, teacher]) => {
    const slots = teacherSlots[teacherId] ?? {};

    days.forEach((day) => {
      periods.forEach((period) => {
        const booked = slots[slotKey(day, period)];
        if (!booked || booked.size === 0) return;

        if (booked.size > 1) {
          const doing = [...booked.values()].map((item) => item.what);
          const violation = {
            type: "teacher_clash",
            scope: "teacher",
            id: teacherId,
            day,
            period,
            message: `${teacher.name} is booked ${booked.size} times at ${day} ${period}: ${doing.join(" and ")}`,
          };
          violations.push(violation);
          addCellConflict(teacherCells, teacherId, day, period, violation);

          // highlight the class cells that caused it
          [...booked.keys()].forEach((unitId) => {
            (classesOfUnitSlot[`${unitId}|${slotKey(day, period)}`] ?? []).forEach(
              (classId) =>
                addCellConflict(classCells, classId, day, period, violation)
            );
          });
        }

        const available = teacher.availability?.[day] ?? [];
        if (!available.includes(period)) {
          const violation = {
            type: "availability_clash",
            scope: "teacher",
            id: teacherId,
            day,
            period,
            message: `${teacher.name} is scheduled at ${day} ${period} but is not available then`,
          };
          violations.push(violation);
          addCellConflict(teacherCells, teacherId, day, period, violation);

          [...booked.keys()].forEach((unitId) => {
            (classesOfUnitSlot[`${unitId}|${slotKey(day, period)}`] ?? []).forEach(
              (classId) =>
                addCellConflict(classCells, classId, day, period, violation)
            );
          });
        }
      });
    });
  });

  // --- required periods per subject -------------------------------------
  const requirementsByClass = {};

  classes.forEach((klass) => {
    const scheduled = {};
    days.forEach((day) => {
      periods.forEach((period) => {
        (klass.grid[day]?.[period] ?? []).forEach((entry) => {
          const key = entry.kind === "band" ? "Second Language" : entry.subject;
          scheduled[key] = (scheduled[key] ?? 0) + 1;
        });
      });
    });

    requirementsByClass[klass.id] = klass.requirements.map((row) => {
      const count = scheduled[row.subject] ?? 0;
      const ok = count === row.required_periods;
      if (!ok) {
        violations.push({
          type: "period_mismatch",
          scope: "class",
          id: klass.id,
          day: null,
          period: null,
          message: `${klass.name}: ${row.subject} needs ${row.required_periods} periods a week but has ${count}`,
        });
      }
      return {
        subject: row.subject,
        required: row.required_periods,
        scheduled: count,
        taughtInLanguageGroups: row.taught_in_language_groups,
        ok,
      };
    });
  });

  const counts = {};
  Object.keys(VIOLATION_LABELS).forEach((type) => {
    counts[type] = violations.filter((item) => item.type === type).length;
  });

  return {
    violations,
    counts,
    total: violations.length,
    classCells,
    teacherCells,
    requirementsByClass,
  };
}
