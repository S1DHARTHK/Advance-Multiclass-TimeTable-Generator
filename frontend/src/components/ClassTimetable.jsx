/**
 * One class's weekly timetable.
 *
 * Days are rows and P1-P7 are columns, so a whole day stays on one
 * horizontal line - the periods are never wrapped onto a second row. The
 * lunch break is its own narrow column between P4 and P5, and the table
 * scrolls sideways inside its own container when the screen is too narrow.
 */

import { Fragment, useState } from "react";

function Cell({ entries, conflicts, onInspect }) {
  const bad = conflicts && conflicts.length > 0;

  if (!entries || entries.length === 0) {
    return (
      <td className={`tt-cell tt-cell--free ${bad ? "tt-cell--clash" : ""}`}>
        <span className="tt-free">—</span>
      </td>
    );
  }

  return (
    <td className={`tt-cell ${bad ? "tt-cell--clash" : ""}`}>
      {entries.map((entry, index) => (
        <div key={index} className="tt-entry">
          <div className="tt-subject">{entry.subject}</div>

          {entry.kind === "band" ? (
            // second language: parallel groups, one teacher per language
            <ul className="tt-groups">
              {entry.members.map((member) => (
                <li key={member.groupId}>
                  {member.subject} · {member.teacherShortName}
                </li>
              ))}
            </ul>
          ) : (
            <div className="tt-teacher">
              {entry.teachers.map((teacher) => teacher.name).join(", ")}
            </div>
          )}
        </div>
      ))}

      {bad && (
        <button type="button" className="tt-flag" onClick={onInspect}>
          ⚠ conflict
        </button>
      )}
    </td>
  );
}

export default function ClassTimetable({ solution, klass, conflicts }) {
  const { days, periods, lunchAfterIndex } = solution;
  const [detail, setDetail] = useState(null);

  return (
    <section className="tt-block">
      <header className="tt-head">
        <h2 className="tt-title">{klass.name}</h2>
        <p className="tt-meta">
          {klass.id}
          {klass.classTeacherName &&
            ` · class teacher ${klass.classTeacherName}`}
        </p>
      </header>

      <div className="tt-scroll">
        <table className="tt-table">
          <thead>
            <tr>
              <th scope="col" className="tt-day-head">
                Day
              </th>
              {periods.map((period, index) => (
                <Fragment key={period}>
                  <th scope="col" className="tt-period-head">
                    {period}
                  </th>
                  {index === lunchAfterIndex && (
                    <th
                      scope="col"
                      className="tt-lunch-head"
                      aria-label="Lunch break"
                    >
                      Lunch
                    </th>
                  )}
                </Fragment>
              ))}
            </tr>
          </thead>

          <tbody>
            {days.map((day) => (
              <tr key={day}>
                <th scope="row" className="tt-day">
                  {day}
                </th>
                {periods.map((period, index) => {
                  const cellConflicts = conflicts?.[day]?.[period] ?? [];
                  return (
                    <Fragment key={period}>
                      <Cell
                        entries={klass.grid[day]?.[period]}
                        conflicts={cellConflicts}
                        onInspect={() =>
                          setDetail({ day, period, items: cellConflicts })
                        }
                      />
                      {index === lunchAfterIndex && (
                        <td className="tt-lunch">
                          <span className="tt-lunch-text">LUNCH BREAK</span>
                        </td>
                      )}
                    </Fragment>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {detail && (
        <div className="detail">
          <div className="detail__head">
            <strong>
              {detail.day} {detail.period}
            </strong>
            <button
              type="button"
              className="detail__close"
              onClick={() => setDetail(null)}
            >
              Close
            </button>
          </div>
          <ul className="detail__list">
            {detail.items.map((item, index) => (
              <li key={index}>{item.message}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
