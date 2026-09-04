/**
 * Timetable data access - the single seam between the UI and its data.
 *
 * The UI never imports mock data directly. It calls generateTimetable(),
 * gets back one normalized object, and renders it. Swapping mock data for
 * a real backend therefore needs no UI changes at all:
 *
 *   1. Create frontend/.env.local containing:
 *        VITE_API_BASE_URL=http://localhost:8000
 *   2. Have the backend answer POST {base}/api/timetable/generate with
 *      JSON in the shape below (any missing field falls back to the
 *      constants from sample_data.py mirrored in data/mockTimetables.js).
 *
 * Expected backend JSON:
 *   {
 *     "className": "+2 Computer Science",
 *     "days":      ["Monday", ...],
 *     "periods":   ["P1", ..., "P7"],
 *     "periodsBeforeLunch": ["P1", "P2", "P3", "P4"],
 *     "slots":     { "Monday": { "P1": "Physics", ... }, ... },
 *     "fitness":   { "score": 100.0, "maxScore": 100,
 *                    "periodViolations": 0, "structuralViolations": 0 }
 *   }
 *
 * Normalized shape handed to the UI:
 *   { id, className, days, periods, periodsBeforeLunch, periodsAfterLunch,
 *     lunchAfterPeriod, slots, fitness, generatedAt, source }
 */

import {
  CLASS_NAME,
  DAYS,
  LUNCH_AFTER_PERIOD,
  MAX_FITNESS,
  MOCK_RUNS,
  PERIODS,
  PERIODS_AFTER_LUNCH,
  PERIODS_BEFORE_LUNCH,
} from "../data/mockTimetables";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

/** True while no backend URL is configured, so the mock data is in use. */
export const usingMockData = API_BASE_URL === "";

const MOCK_DELAY_MS = 700;

/**
 * Turn a raw run (mock or backend) into the object the UI renders.
 * Missing structural fields fall back to the known timetable shape.
 */
export function normalizeTimetable(raw, source = "mock") {
  const periods = raw.periods ?? PERIODS;
  const periodsBeforeLunch = raw.periodsBeforeLunch ?? PERIODS_BEFORE_LUNCH;
  const periodsAfterLunch =
    raw.periodsAfterLunch ??
    (raw.periodsBeforeLunch
      ? periods.filter((p) => !periodsBeforeLunch.includes(p))
      : PERIODS_AFTER_LUNCH);

  const fitness = raw.fitness ?? {};

  return {
    id: raw.id ?? `timetable-${Date.now()}`,
    className: raw.className ?? CLASS_NAME,
    days: raw.days ?? DAYS,
    periods,
    periodsBeforeLunch,
    periodsAfterLunch,
    lunchAfterPeriod:
      raw.lunchAfterPeriod ??
      periodsBeforeLunch[periodsBeforeLunch.length - 1] ??
      LUNCH_AFTER_PERIOD,
    slots: raw.slots ?? {},
    fitness: {
      score: fitness.score ?? 0,
      maxScore: fitness.maxScore ?? MAX_FITNESS,
      periodViolations: fitness.periodViolations ?? 0,
      structuralViolations: fitness.structuralViolations ?? 0,
    },
    generatedAt: raw.generatedAt ?? new Date().toISOString(),
    source,
  };
}

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Cycles through the recorded GA runs so "Regenerate" shows a new timetable.
let mockRunIndex = -1;

async function generateFromMock() {
  await delay(MOCK_DELAY_MS);
  mockRunIndex = (mockRunIndex + 1) % MOCK_RUNS.length;
  return normalizeTimetable(MOCK_RUNS[mockRunIndex], "mock");
}

async function generateFromApi() {
  const response = await fetch(`${API_BASE_URL}/api/timetable/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });

  if (!response.ok) {
    throw new Error(`Timetable service responded with ${response.status}`);
  }

  return normalizeTimetable(await response.json(), "api");
}

/** Generate a timetable. Same promise contract for mock and backend. */
export function generateTimetable() {
  return usingMockData ? generateFromMock() : generateFromApi();
}
