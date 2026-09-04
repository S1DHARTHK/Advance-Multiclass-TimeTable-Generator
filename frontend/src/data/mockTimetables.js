/**
 * Mock timetable data - Phase 1 output.
 *
 * These three timetables are the actual results of running the Phase 1
 * Python GA (genetic_algorithm.py) with random seeds 42, 7 and 2024.
 * Every run reached the maximum fitness of 100.00 with zero violations.
 *
 * This file is the ONLY place mock data lives. When the backend is ready,
 * nothing here needs to change - src/api/timetableApi.js simply stops
 * reading from it (see the notes in that file).
 */

// Timetable shape constants, mirroring sample_data.py.
export const CLASS_NAME = "+2 Computer Science";
export const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
export const PERIODS = ["P1", "P2", "P3", "P4", "P5", "P6", "P7"];
export const PERIODS_BEFORE_LUNCH = ["P1", "P2", "P3", "P4"];
export const PERIODS_AFTER_LUNCH = ["P5", "P6", "P7"];
export const LUNCH_AFTER_PERIOD = "P4";
export const MAX_FITNESS = 100;

/**
 * Raw runs, in the same shape a backend response is expected to use.
 * See normalizeTimetable() in src/api/timetableApi.js for the contract.
 */
export const MOCK_RUNS = [
  {
    id: "run-1",
    className: CLASS_NAME,
    fitness: { score: 100.0, maxScore: 100, periodViolations: 0, structuralViolations: 0 },
    slots: {
      Monday: {
        P1: "Physics",
        P2: "Computer Science",
        P3: "Mathematics",
        P4: "Computer Science",
        P5: "English",
        P6: "Chemistry",
        P7: "Hindi",
      },
      Tuesday: {
        P1: "Physics",
        P2: "Computer Science",
        P3: "Mathematics",
        P4: "Physics",
        P5: "Chemistry",
        P6: "Physics",
        P7: "Hindi",
      },
      Wednesday: {
        P1: "Physics",
        P2: "Mathematics",
        P3: "Mathematics",
        P4: "Chemistry",
        P5: "English",
        P6: "Physics",
        P7: "Hindi",
      },
      Thursday: {
        P1: "Chemistry",
        P2: "Computer Science",
        P3: "Mathematics",
        P4: "Chemistry",
        P5: "English",
        P6: "Mathematics",
        P7: "English",
      },
      Friday: {
        P1: "Chemistry",
        P2: "Computer Science",
        P3: "Computer Science",
        P4: "Mathematics",
        P5: "English",
        P6: "Computer Science",
        P7: "Hindi",
      },
    },
  },
  {
    id: "run-2",
    className: CLASS_NAME,
    fitness: { score: 100.0, maxScore: 100, periodViolations: 0, structuralViolations: 0 },
    slots: {
      Monday: {
        P1: "Physics",
        P2: "Mathematics",
        P3: "Computer Science",
        P4: "Physics",
        P5: "English",
        P6: "Computer Science",
        P7: "Hindi",
      },
      Tuesday: {
        P1: "Chemistry",
        P2: "Computer Science",
        P3: "Computer Science",
        P4: "Physics",
        P5: "Physics",
        P6: "Computer Science",
        P7: "Hindi",
      },
      Wednesday: {
        P1: "Chemistry",
        P2: "Mathematics",
        P3: "Mathematics",
        P4: "Physics",
        P5: "English",
        P6: "Chemistry",
        P7: "Hindi",
      },
      Thursday: {
        P1: "Chemistry",
        P2: "Computer Science",
        P3: "Mathematics",
        P4: "Physics",
        P5: "English",
        P6: "Chemistry",
        P7: "Hindi",
      },
      Friday: {
        P1: "Chemistry",
        P2: "Mathematics",
        P3: "Mathematics",
        P4: "Mathematics",
        P5: "English",
        P6: "Computer Science",
        P7: "English",
      },
    },
  },
  {
    id: "run-3",
    className: CLASS_NAME,
    fitness: { score: 100.0, maxScore: 100, periodViolations: 0, structuralViolations: 0 },
    slots: {
      Monday: {
        P1: "Chemistry",
        P2: "Computer Science",
        P3: "Mathematics",
        P4: "Chemistry",
        P5: "English",
        P6: "Computer Science",
        P7: "Hindi",
      },
      Tuesday: {
        P1: "Chemistry",
        P2: "Computer Science",
        P3: "Computer Science",
        P4: "Computer Science",
        P5: "English",
        P6: "Physics",
        P7: "English",
      },
      Wednesday: {
        P1: "Physics",
        P2: "Mathematics",
        P3: "Mathematics",
        P4: "Chemistry",
        P5: "English",
        P6: "Physics",
        P7: "Hindi",
      },
      Thursday: {
        P1: "Chemistry",
        P2: "Computer Science",
        P3: "Computer Science",
        P4: "Physics",
        P5: "Physics",
        P6: "Mathematics",
        P7: "Hindi",
      },
      Friday: {
        P1: "Physics",
        P2: "Mathematics",
        P3: "Mathematics",
        P4: "Chemistry",
        P5: "English",
        P6: "Mathematics",
        P7: "Hindi",
      },
    },
  },
];
