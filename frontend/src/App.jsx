import { useCallback, useEffect, useMemo, useState } from "react";

import ClashStatus from "./components/ClashStatus";
import ClassTimetable from "./components/ClassTimetable";
import EditDialog from "./components/EditDialog";
import SubjectRequirements from "./components/SubjectRequirements";
import TeacherSchedule from "./components/TeacherSchedule";
import { loadSolution, normalizeSolution } from "./api/solutionApi";
import { validateSolution } from "./validation";

const ALL_CLASSES = "ALL";
const CLASS_VIEW = "class";
const TEACHER_VIEW = "teacher";

export default function App() {
  const [solution, setSolution] = useState(null);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState(null);

  const [view, setView] = useState(CLASS_VIEW);
  const [selectedClass, setSelectedClass] = useState(ALL_CLASSES);
  const [selectedTeacher, setSelectedTeacher] = useState("");
  const [editing, setEditing] = useState(null);

  // The timetable comes from the editor service when it is running, and
  // from the bundled file otherwise (read-only).
  useEffect(() => {
    let cancelled = false;

    loadSolution().then(({ solution: loaded, live: isLive }) => {
      if (cancelled) return;
      setSolution(loaded);
      setLive(isLive);
      setLoading(false);
      setSelectedClass(loaded.classes[0]?.id ?? ALL_CLASSES);
      const first = Object.values(loaded.teachers).sort((a, b) =>
        a.name.localeCompare(b.name)
      )[0];
      setSelectedTeacher(first?.id ?? "");
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const validation = useMemo(
    () => (solution ? validateSolution(solution) : null),
    [solution]
  );

  const teacherList = useMemo(
    () =>
      solution
        ? Object.values(solution.teachers).sort((a, b) =>
            a.name.localeCompare(b.name)
          )
        : [],
    [solution]
  );

  // One state update refreshes every view, class and teacher alike, because
  // they all read from this object.
  const handleApplied = useCallback((result) => {
    setSolution(normalizeSolution(result.solution));
    setEditing(null);
    setNotice(
      `Applied: ${result.applied.summary} — timetable now ${result.report.hard_total} violations, soft ${result.report.soft_total.toFixed(2)}.`
    );
  }, []);

  if (loading) {
    return (
      <div className="page">
        <div className="panel panel--empty">
          <div className="spinner" aria-hidden="true" />
          <h2>Loading timetable</h2>
        </div>
      </div>
    );
  }

  const shownClasses =
    selectedClass === ALL_CLASSES
      ? solution.classes
      : solution.classes.filter((klass) => klass.id === selectedClass);

  const teacher = solution.teachers[selectedTeacher];

  return (
    <div className="page">
      <header className="header">
        <div className="header__text">
          <p className="header__eyebrow">Generated timetable</p>
          <h1 className="header__title">+2 Weekly Timetable</h1>
          <p className="header__subtitle">
            {solution.classes.length} classes &middot; {teacherList.length}{" "}
            teachers &middot; Monday to Friday &middot;{" "}
            {solution.periods.length} periods a day
          </p>
        </div>

        <div className="header__actions">
          <div className="views" role="group" aria-label="View">
            <button
              type="button"
              className={`views__button ${view === CLASS_VIEW ? "is-active" : ""}`}
              onClick={() => setView(CLASS_VIEW)}
            >
              Class View
            </button>
            <button
              type="button"
              className={`views__button ${view === TEACHER_VIEW ? "is-active" : ""}`}
              onClick={() => setView(TEACHER_VIEW)}
            >
              Teacher View
            </button>
          </div>

          {view === CLASS_VIEW ? (
            <label className="picker">
              <span className="picker__label">Class</span>
              <select
                className="picker__select"
                value={selectedClass}
                onChange={(event) => setSelectedClass(event.target.value)}
              >
                <option value={ALL_CLASSES}>All Classes</option>
                {solution.classes.map((klass) => (
                  <option key={klass.id} value={klass.id}>
                    {klass.name}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <label className="picker">
              <span className="picker__label">Teacher</span>
              <select
                className="picker__select"
                value={selectedTeacher}
                onChange={(event) => setSelectedTeacher(event.target.value)}
              >
                {teacherList.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} — {item.department}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      </header>

      <main className="content">
        <ClashStatus validation={validation} softReport={solution.softReport} />

        {notice && (
          <p className="notice notice--ok">
            {notice}
            <button
              type="button"
              className="notice__close"
              onClick={() => setNotice(null)}
            >
              Dismiss
            </button>
          </p>
        )}

        {!live && (
          <p className="notice">
            Showing the saved timetable. Start the editor service
            (<code>python editor_server.py</code>) to edit lessons.
          </p>
        )}

        {view === CLASS_VIEW &&
          shownClasses.map((klass) => (
            <ClassTimetable
              key={klass.id}
              solution={solution}
              klass={klass}
              conflicts={validation.classCells[klass.id]}
            />
          ))}

        {view === CLASS_VIEW && selectedClass !== ALL_CLASSES && (
          <SubjectRequirements
            rows={validation.requirementsByClass[selectedClass] ?? []}
          />
        )}

        {view === TEACHER_VIEW && teacher && (
          <TeacherSchedule
            solution={solution}
            teacher={teacher}
            conflicts={validation.teacherCells[teacher.id]}
            onEdit={live ? (cell) => setEditing({ ...cell, teacherId: teacher.id }) : null}
          />
        )}
      </main>

      {editing && (
        <EditDialog
          teacherId={editing.teacherId}
          day={editing.day}
          period={editing.period}
          onClose={() => setEditing(null)}
          onApplied={handleApplied}
        />
      )}
    </div>
  );
}
