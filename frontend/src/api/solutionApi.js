/**
 * Timetable solution data access.
 *
 * The UI never reads the raw GA output directly - it calls loadSolution()
 * and renders one normalized object. Swapping the bundled file for a
 * backend needs no UI changes:
 *
 *   const raw = await fetch(`${base}/api/timetable/latest`).then(r => r.json());
 *   return normalizeSolution(raw);
 *
 * Input is whatever ga_v1.py writes to timetable_solution.json.
 */

import rawSolution from "../data/timetableSolution.json";
import { editorApi } from "./editorApi";

/** "Vishnu Suresh" -> "V. Suresh", to keep cells narrow. */
function shortName(name) {
  if (!name) return "";
  const parts = name.trim().split(/\s+/);
  if (parts.length < 2) return name;
  return `${parts[0][0]}. ${parts[parts.length - 1]}`;
}

function normalizeCell(entry, teacherNames) {
  const teachers = (entry.teachers ?? []).map((id) => ({
    id,
    name: teacherNames[id] ?? id,
    shortName: shortName(teacherNames[id]) || id,
  }));

  // A band cell covers several parallel language groups, so keep the
  // per-group detail: students of one class split across those groups.
  const members = (entry.members ?? []).map((member) => ({
    subject: member.subject,
    groupId: member.group_id,
    teacherId: member.teacher_id,
    teacherName: teacherNames[member.teacher_id] ?? member.teacher_id,
    teacherShortName:
      shortName(teacherNames[member.teacher_id]) || member.teacher_id,
  }));

  return {
    unitId: entry.unit_id,
    kind: entry.kind,
    subject: entry.subject,
    classIds: entry.classes ?? [],
    groupIds: entry.groups ?? [],
    teachers,
    members,
  };
}

export function normalizeSolution(raw) {
  const structure = raw.structure ?? {};
  const days = structure.days ?? [];
  const periods = structure.periods ?? [];
  const lunchAfterPeriod = structure.lunch_after_period ?? null;

  const teacherNames = {};
  Object.entries(raw.teachers ?? {}).forEach(([id, teacher]) => {
    teacherNames[id] = teacher.name;
  });

  const classes = Object.entries(raw.classes ?? {}).map(([id, klass]) => {
    const grid = {};
    days.forEach((day) => {
      grid[day] = {};
      periods.forEach((period) => {
        const cell = klass.timetable?.[day]?.[period] ?? [];
        grid[day][period] = cell.map((entry) =>
          normalizeCell(entry, teacherNames)
        );
      });
    });

    return {
      id,
      name: klass.name,
      classTeacherId: klass.class_teacher_id ?? null,
      classTeacherName: teacherNames[klass.class_teacher_id] ?? null,
      requirements: klass.requirements ?? [],
      grid,
    };
  });

  // teachers, with their own week and when they may work
  const teachers = {};
  Object.entries(raw.teachers ?? {}).forEach(([id, teacher]) => {
    const grid = {};
    days.forEach((day) => {
      grid[day] = {};
      periods.forEach((period) => {
        const cell = teacher.timetable?.[day]?.[period] ?? [];
        grid[day][period] = cell.map((entry) =>
          normalizeCell(entry, teacherNames)
        );
      });
    });

    teachers[id] = {
      id,
      name: teacher.name,
      department: teacher.department,
      maxWeeklyPeriods: teacher.max_weekly_periods ?? null,
      availability: teacher.availability ?? {},
      grid,
    };
  });

  return {
    days,
    periods,
    lunchAfterPeriod,
    // index of the period the lunch break follows, so the grid can put the
    // break between P4 and P5 without hard-coding either name
    lunchAfterIndex: periods.indexOf(lunchAfterPeriod),
    classes,
    teachers,
    // soft scores stay exactly where they belong: quality reporting, kept
    // apart from the hard-constraint check in validation.js
    softReport: {
      total: raw.report?.soft_total ?? null,
      max: Object.values(raw.report?.soft_weights ?? {}).reduce(
        (sum, weight) => sum + weight,
        0
      ),
      scores: raw.report?.soft_scores ?? {},
      weights: raw.report?.soft_weights ?? {},
    },
  };
}

/**
 * Load the timetable, preferring the live editor service.
 *
 * With the service running the timetable can be edited; without it the
 * bundled file is still shown, read-only. `live` says which happened.
 */
export async function loadSolution() {
  try {
    const raw = await editorApi.solution();
    return { solution: normalizeSolution(raw), live: true, error: null };
  } catch (error) {
    return {
      solution: normalizeSolution(rawSolution),
      live: false,
      error: error.message,
    };
  }
}

/** The bundled snapshot, without any network call. */
export function loadBundledSolution() {
  return normalizeSolution(rawSolution);
}
