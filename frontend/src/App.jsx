import { useMemo, useState } from "react";

import ClashStatus from "./components/ClashStatus";
import ClassTimetable from "./components/ClassTimetable";
import SubjectRequirements from "./components/SubjectRequirements";
import TeacherSchedule from "./components/TeacherSchedule";
import { loadSolution } from "./api/solutionApi";
import { validateSolution } from "./validation";

const ALL_CLASSES = "ALL";
const CLASS_VIEW = "class";
const TEACHER_VIEW = "teacher";

export default function App() {
  // The generated timetable never changes while the page is open, so it is
  // read and checked once. Swap loadSolution() for a fetch when a backend
  // exists; nothing else here changes.
  const solution = useMemo(() => loadSolution(), []);
  const validation = useMemo(() => validateSolution(solution), [solution]);

  const teacherList = useMemo(
    () =>
      Object.values(solution.teachers).sort((a, b) =>
        a.name.localeCompare(b.name)
      ),
    [solution]
  );

  const [view, setView] = useState(CLASS_VIEW);
  const [selectedClass, setSelectedClass] = useState(
    solution.classes[0]?.id ?? ALL_CLASSES
  );
  const [selectedTeacher, setSelectedTeacher] = useState(
    teacherList[0]?.id ?? ""
  );

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

        {view === CLASS_VIEW &&
          shownClasses.map((klass) => (
            <ClassTimetable
              key={klass.id}
              solution={solution}
              klass={klass}
              conflicts={validation.classCells[klass.id]}
            />
          ))}

        {/* requirements belong to one class, so they show for a single class */}
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
          />
        )}
      </main>
    </div>
  );
}
