/**
 * One teacher's whole week: Monday-Friday as rows, P1-P7 as columns, with
 * the lunch break between P4 and P5 and each day on a single row.
 *
 * Underneath, the daily load so workload distribution is readable at a
 * glance. Conflicting cells are highlighted and can be clicked for details.
 */

import { Fragment, useState } from "react";

function cellLabel(entry) {
  // in a band the teacher takes one group; elsewhere it is a class lesson
  if (entry.kind === "band") {
    const member = entry.members[0];
    return {
      where: member?.groupId ?? "Language group",
      subject: member?.subject ?? entry.subject,
    };
  }
  return { where: entry.classIds[0] ?? "", subject: entry.subject };
}

export default function TeacherSchedule({ solution, teacher, conflicts }) {
  const { days, periods, lunchAfterIndex } = solution;
  const [detail, setDetail] = useState(null);

  const perDay = days.map((day) => {
    const entries = periods.flatMap(
      (period) => teacher.grid[day]?.[period] ?? []
    );
    // in a band this teacher takes only their own group, so count that -
    // not every group running in parallel
    const classIds = new Set(
      entries.flatMap((entry) =>
        entry.kind === "band"
          ? entry.members.map((member) => member.groupId)
          : entry.classIds
      )
    );
    return { day, periods: entries.length, groups: classIds.size };
  });

  const weekTotal = perDay.reduce((sum, row) => sum + row.periods, 0);
  const busiest = Math.max(1, ...perDay.map((row) => row.periods));

  return (
    <section className="tt-block">
      <header className="tt-head">
        <h2 className="tt-title">{teacher.name}</h2>
        <p className="tt-meta">
          {teacher.id} · {teacher.department} · {weekTotal} periods this week
          {teacher.maxWeeklyPeriods ? ` of ${teacher.maxWeeklyPeriods} allowed` : ""}
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
                    <th scope="col" className="tt-lunch-head">
                      Lunch
                    </th>
                  )}
                </Fragment>
              ))}
              <th scope="col" className="tt-period-head">
                Day total
              </th>
            </tr>
          </thead>

          <tbody>
            {days.map((day, dayIndex) => (
              <tr key={day}>
                <th scope="row" className="tt-day">
                  {day}
                </th>

                {periods.map((period, index) => {
                  const entries = teacher.grid[day]?.[period] ?? [];
                  const cellConflicts = conflicts?.[day]?.[period] ?? [];
                  const bad = cellConflicts.length > 0;

                  return (
                    <Fragment key={period}>
                      <td className={`tt-cell ${bad ? "tt-cell--clash" : ""}`}>
                        {entries.length === 0 ? (
                          <span className="tt-free">—</span>
                        ) : (
                          entries.map((entry, entryIndex) => {
                            const { where, subject } = cellLabel(entry);
                            return (
                              <div key={entryIndex} className="tt-entry">
                                <div className="tt-subject">{subject}</div>
                                <div className="tt-teacher">{where}</div>
                              </div>
                            );
                          })
                        )}
                        {bad && (
                          <button
                            type="button"
                            className="tt-flag"
                            onClick={() =>
                              setDetail({ day, period, items: cellConflicts })
                            }
                          >
                            ⚠ conflict
                          </button>
                        )}
                      </td>

                      {index === lunchAfterIndex && (
                        <td className="tt-lunch">
                          <span className="tt-lunch-text">LUNCH BREAK</span>
                        </td>
                      )}
                    </Fragment>
                  );
                })}

                <td className="tt-total">
                  <span className="tt-total__value">
                    {perDay[dayIndex].periods}
                  </span>
                  <span
                    className="tt-total__bar"
                    style={{
                      width: `${(perDay[dayIndex].periods / busiest) * 100}%`,
                    }}
                  />
                  <span className="tt-total__note">
                    {perDay[dayIndex].groups} class
                    {perDay[dayIndex].groups === 1 ? "" : "es"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>

          <tfoot>
            <tr>
              <th scope="row" className="tt-day">
                Week
              </th>
              <td
                className="tt-weektotal"
                colSpan={periods.length + 1}
              >
                {weekTotal} periods across {perDay.filter((row) => row.periods).length}{" "}
                teaching days
              </td>
              <td className="tt-total">
                <span className="tt-total__value">{weekTotal}</span>
              </td>
            </tr>
          </tfoot>
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
