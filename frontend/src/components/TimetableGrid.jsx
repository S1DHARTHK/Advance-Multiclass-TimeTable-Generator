/**
 * The timetable itself: days as rows, periods as columns.
 *
 * The grid is split into a morning block (P1-P4) and an afternoon block
 * (P5-P7) with a full-width LUNCH BREAK row between them. Lunch is a
 * visual divider only - it is never one of the 7 periods.
 */

const SUBJECT_KEYS = {
  Physics: "physics",
  Chemistry: "chemistry",
  Mathematics: "mathematics",
  "Computer Science": "computer-science",
  Hindi: "hindi",
  English: "english",
};

function SubjectCell({ subject }) {
  if (!subject || subject === "Free") {
    return (
      <td className="cell cell--free">
        <span className="subject subject--free">Free</span>
      </td>
    );
  }

  return (
    <td className="cell">
      <span className="subject" data-subject={SUBJECT_KEYS[subject] ?? "other"}>
        {subject}
      </span>
    </td>
  );
}

function DayRows({ days, periods, slots, columnCount }) {
  // Keep both blocks on the same column widths by padding the shorter one.
  const padding = Math.max(0, columnCount - periods.length);

  return days.map((day) => (
    <tr key={day}>
      <th scope="row" className="day-cell">
        {day}
      </th>
      {periods.map((period) => (
        <SubjectCell key={period} subject={slots[day]?.[period]} />
      ))}
      {Array.from({ length: padding }, (_, i) => (
        <td key={`pad-${i}`} className="cell cell--pad" aria-hidden="true" />
      ))}
    </tr>
  ));
}

function PeriodHeader({ label, periods, columnCount }) {
  const padding = Math.max(0, columnCount - periods.length);

  return (
    <tr className="period-header">
      <th scope="col" className="day-cell day-cell--head">
        {label}
      </th>
      {periods.map((period) => (
        <th scope="col" key={period} className="period-cell">
          {period}
        </th>
      ))}
      {Array.from({ length: padding }, (_, i) => (
        <th key={`pad-${i}`} className="period-cell period-cell--pad" aria-hidden="true" />
      ))}
    </tr>
  );
}

export default function TimetableGrid({ timetable }) {
  const { days, periodsBeforeLunch, periodsAfterLunch, slots } = timetable;

  // Widest block decides the column count; the other block is padded.
  const columnCount = Math.max(periodsBeforeLunch.length, periodsAfterLunch.length);
  const totalColumns = columnCount + 1; // + the day-name column

  return (
    <div className="grid-scroll">
      <table className="timetable">
        <caption className="sr-only">
          Weekly timetable for {timetable.className}
        </caption>

        <thead>
          <PeriodHeader
            label="Before lunch"
            periods={periodsBeforeLunch}
            columnCount={columnCount}
          />
        </thead>

        <tbody>
          <DayRows
            days={days}
            periods={periodsBeforeLunch}
            slots={slots}
            columnCount={columnCount}
          />

          <tr className="lunch-row">
            <td colSpan={totalColumns}>
              <span className="lunch-label">LUNCH BREAK</span>
              <span className="lunch-note">not a teaching period</span>
            </td>
          </tr>

          <PeriodHeader
            label="After lunch"
            periods={periodsAfterLunch}
            columnCount={columnCount}
          />

          <DayRows
            days={days}
            periods={periodsAfterLunch}
            slots={slots}
            columnCount={columnCount}
          />
        </tbody>
      </table>
    </div>
  );
}
