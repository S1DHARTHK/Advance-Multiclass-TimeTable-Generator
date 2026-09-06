/**
 * One teacher's whole week: Monday-Friday as rows, P1-P7 as columns, with
 * the lunch break between P4 and P5 and each day on a single row.
 *
 * Underneath, the daily load so workload distribution is readable at a
 * glance. Conflicting cells are highlighted and can be clicked for details.
 *
 * Edit mode
 *     Pressing Edit on a lesson paints every slot it could legally move to
 *     straight onto this grid, shaded from green (best option) to red
 *     (worst). Each shaded slot carries its own Details button; the full
 *     ranked list sits behind a button at the top right of the timetable.
 */

import { Fragment, useMemo, useState } from "react";

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

export const optionKey = (option) =>
  `${option.day}|${option.period}|${option.kind}`;

/** "More details" - an info mark, so the slot reads as something to open. */
function InfoIcon() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" focusable="false">
      <circle cx="12" cy="12" r="9.25" fill="none" stroke="currentColor" strokeWidth="1.9" />
      <circle cx="12" cy="7.9" r="1.25" fill="currentColor" />
      <path
        d="M12 11.2v5.4"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * Best -> worst, run across the project palette:
 *
 *   Topiary Sculpture -> Tree Shade -> Treetop Cathedral
 *   -> Lindworm Green -> Jester Red
 *
 * The best option wears the liveliest green, options dim through the
 * darker greens as they get worse, and the worst lands on red. The shade
 * follows an option's real score relative to the best and worst on offer,
 * so equally good options look equally good.
 */
/**
 * Aurora ranking scale: five named tiers rather than a smooth ramp, so a
 * card's standing reads at a glance instead of being guessed from a shade.
 *
 * The hue travels teal -> cyan -> indigo -> purple -> rose. Deliberately
 * not a traffic light: none of these is a warning colour, and all five sit
 * dark enough to carry white text on the black page.
 */
const TIERS = [
  { name: "Best", fill: [0x19, 0x39, 0x21] }, // deep green   #193921
  { name: "Good", fill: [0x40, 0x84, 0x35] }, // green        #408435
  { name: "Fair", fill: [0x7c, 0x88, 0x40] }, // olive        #7C8840
  { name: "Poor", fill: [0x88, 0x60, 0x2d] }, // amber-brown  #88602D
  { name: "Worst", fill: [0x88, 0x3b, 0x2d] }, // red-brown    #883B2D
];

/** Which tier a 0 (best) .. 1 (worst) score falls into. */
export function tierFor(ratio) {
  const clamped = Math.min(1, Math.max(0, ratio));
  return TIERS[Math.min(TIERS.length - 1, Math.floor(clamped * TIERS.length))];
}

/** Perceived brightness, to decide what ink a card can carry. */
function luminance([r, g, b]) {
  const channel = (value) => {
    const scaled = value / 255;
    return scaled <= 0.03928
      ? scaled / 12.92
      : ((scaled + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function tintFor(ratio) {
  const channels = tierFor(ratio).fill;

  // Every tier here is dark, so white wins - but the check stays so a
  // future palette with light tones still gets a readable ink.
  const fill = luminance(channels);
  const contrast = (other) =>
    (Math.max(fill, other) + 0.05) / (Math.min(fill, other) + 0.05);

  const darkInk = luminance([0x16, 0x20, 0x1a]);
  const useDarkInk = contrast(darkInk) >= contrast(1);
  const ink = useDarkInk ? "#16201a" : "#ffffff";

  // border and glow are the tier's own hue lifted towards light: enough to
  // outline the card and give it a faint aurora edge, not enough to read
  // as an alert
  const lift = (amount) =>
    channels.map((value) =>
      useDarkInk
        ? Math.round(value * (1 - amount))
        : Math.round(value + (255 - value) * amount)
    );

  const background = `rgb(${channels.join(", ")})`;
  const edge = lift(0.3);
  const glow = lift(0.55);

  return {
    background,
    borderColor: `rgb(${edge.join(", ")})`,
    color: ink,
    "--on-tint": ink,
    "--tint-bg": background,
    "--tint-edge": `rgb(${edge.join(", ")})`,
    "--tint-glow": `rgba(${glow.join(", ")}, 0.42)`,
    "--chip": useDarkInk ? "rgba(0, 0, 0, 0.12)" : "rgba(255, 255, 255, 0.14)",
  };
}

export default function TeacherSchedule({
  solution,
  teacher,
  conflicts,
  onEdit,
  editor,
}) {
  const { days, periods, lunchAfterIndex } = solution;
  const [detail, setDetail] = useState(null);
  const [openOption, setOpenOption] = useState(null);

  const session = editor?.session;
  const ready = session?.status === "ready" ? session : null;

  // slot -> option, with a 0..1 ratio of how good it is (0 = best)
  const optionBySlot = useMemo(() => {
    const map = {};
    if (!ready) return map;

    const scores = ready.data.candidates.map((item) => item.fitness_delta);
    const best = Math.max(...scores);
    const worst = Math.min(...scores);
    const span = best - worst;

    ready.data.candidates.forEach((option, index) => {
      const ratio = span > 1e-9 ? (best - option.fitness_delta) / span : 0;
      map[`${option.day}|${option.period}`] = {
        ...option,
        rank: index + 1,
        ratio,
        tier: tierFor(ratio).name,
      };
    });
    return map;
  }, [ready]);

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

  const preview =
    openOption && editor?.preview?.key === optionKey(openOption)
      ? editor.preview.data
      : null;

  return (
    <section className="tt-block">
      <header className="tt-head tt-head--split">
        <div>
          <h2 className="tt-title">{teacher.name}</h2>
          <p className="tt-meta">
            {teacher.id} · {teacher.department} · {weekTotal} periods this week
            {teacher.maxWeeklyPeriods
              ? ` of ${teacher.maxWeeklyPeriods} allowed`
              : ""}
          </p>
        </div>

        {/* edit toolbar, top right and next to the grid it acts on */}
        {session && (
          <div className="editbar">
            {session.status === "loading" && (
              <span className="editbar__note">Checking every slot…</span>
            )}

            {session.status === "error" && (
              <span className="editbar__error">{session.error}</span>
            )}

            {ready && (
              <>
                <span className="editbar__note">
                  Moving <strong>{ready.data.current.subject}</strong> ·{" "}
                  {ready.data.current.target} from {ready.data.current.day}{" "}
                  {ready.data.current.period}
                </span>

                <span className="legend" aria-hidden="true">
                  <span className="legend__label">best</span>
                  <span className="legend__bar" />
                  <span className="legend__label">worst</span>
                </span>

                <button
                  type="button"
                  className="button button--small"
                  onClick={editor.openAll}
                >
                  All options ({ready.data.candidates.length})
                </button>
              </>
            )}

            <button
              type="button"
              className="button button--small"
              onClick={() => {
                setOpenOption(null);
                editor.cancel();
              }}
            >
              Cancel
            </button>
          </div>
        )}
      </header>

      {/* grid on the left, the open slot's details alongside it on the right */}
      <div className="tt-layout">
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

                  const option = optionBySlot[`${day}|${period}`];
                  const isCurrent =
                    ready &&
                    ready.data.current.day === day &&
                    ready.data.current.period === period;
                  const isOpen =
                    Boolean(option) &&
                    Boolean(openOption) &&
                    optionKey(openOption) === optionKey(option);

                  // don't repeat a lesson this teacher already teaches here
                  const showsPartner =
                    Boolean(option?.partner) &&
                    !entries.some(
                      (entry) => entry.unitId === option.partner.unit_id
                    );

                  const classes = ["tt-cell"];
                  if (bad) classes.push("tt-cell--clash");
                  if (option) classes.push("tt-cell--option");
                  if (isCurrent) classes.push("tt-cell--current");
                  if (isOpen) classes.push("tt-cell--chosen");

                  return (
                    <Fragment key={period}>
                      <td className={classes.join(" ")}>
                        {/* a candidate's colour, border, radius and shadow
                            live on an inner card: a <td> in a collapsed
                            table cannot round its own corners */}
                        <div
                          className={option ? "tt-option-box" : "tt-plain"}
                          style={option ? tintFor(option.ratio) : undefined}
                        >
                        {entries.length === 0 && !option && (
                          <span className="tt-free">—</span>
                        )}

                        {entries.map((entry, entryIndex) => {
                          const { where, subject } = cellLabel(entry);
                          return (
                            <div key={entryIndex} className="tt-entry">
                              <div className="tt-subject">{subject}</div>
                              <div className="tt-teacher">{where}</div>
                            </div>
                          );
                        })}

                        {/* What already sits in this period. Usually another
                            teacher's lesson, so it is not in this grid - but
                            it is what the move would displace. */}
                        {option && showsPartner && (
                          <div className="tt-swapinfo">
                            <span className="tt-swapinfo__subject">
                              {option.partner.subject}
                            </span>
                            <span className="tt-swapinfo__target">
                              {option.partner.target}
                            </span>
                          </div>
                        )}

                        {option && !option.partner && (
                          <div className="tt-swapinfo">
                            <span className="tt-swapinfo__free">
                              Free period
                            </span>
                          </div>
                        )}

                        {isCurrent && (
                          <span className="tt-tagline">moving from here</span>
                        )}

                        {option && (
                          <button
                            type="button"
                            className={`tt-option-info${isOpen ? " is-open" : ""}`}
                            onClick={() => {
                              setOpenOption(isOpen ? null : option);
                              setDetail(null);
                            }}
                            aria-expanded={isOpen}
                            title={`${option.tier} · option #${option.rank} · ${
                              option.kind === "swap" ? "Swap" : "Move"
                            } · impact ${
                              option.soft_delta >= 0 ? "+" : ""
                            }${option.soft_delta.toFixed(2)} — view details`}
                            aria-label={`Option ${option.rank}, ${
                              option.kind
                            }, impact ${option.soft_delta.toFixed(
                              2
                            )}. View details`}
                          >
                            <InfoIcon />
                          </button>
                        )}

                        {/* straight to it: applies this option without
                            opening the details first */}
                        {option && (
                          <button
                            type="button"
                            className="tt-swap"
                            onClick={() => editor.applyOption(option)}
                            disabled={editor.busy}
                            title={`${
                              option.kind === "swap"
                                ? `Swap with ${option.partner?.subject ?? "this lesson"}`
                                : "Move here"
                            } now · impact ${
                              option.soft_delta >= 0 ? "+" : ""
                            }${option.soft_delta.toFixed(2)}`}
                          >
                            {editor.busy
                              ? "…"
                              : option.kind === "swap"
                                ? "Swap"
                                : "Move"}
                          </button>
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

                        {entries.length > 0 && onEdit && !session && (
                          <button
                            type="button"
                            className="tt-edit"
                            onClick={() => onEdit({ day, period })}
                            title="Find a better slot for this lesson"
                          >
                            Edit
                          </button>
                        )}
                        </div>
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
              <td className="tt-weektotal" colSpan={periods.length + 1}>
                {weekTotal} periods across{" "}
                {perDay.filter((row) => row.periods).length} teaching days
              </td>
              <td className="tt-total">
                <span className="tt-total__value">{weekTotal}</span>
              </td>
            </tr>
          </tfoot>
          </table>
        </div>

        {/* details for one shaded slot: what sits there now and what swaps */}
      {openOption && ready && (
        <aside className="slotdetail" style={tintFor(openOption.ratio)}>
          <div className="slotdetail__head">
            <strong>
              #{openOption.rank} · {openOption.day} {openOption.period}
            </strong>
            <span className="tier">{openOption.tier}</span>
            <span className={`badge badge--${openOption.kind}`}>
              {openOption.kind === "swap" ? "Swap" : "Move"}
            </span>
            <span className="badge badge--ok">✓ No clashes</span>
            <button
              type="button"
              className="detail__close"
              onClick={() => setOpenOption(null)}
            >
              Close
            </button>
          </div>

          <dl className="slotdetail__grid">
            <div>
              <dt>This lesson</dt>
              <dd>
                {ready.data.current.subject} · {ready.data.current.target}
                <br />
                {ready.data.current.day} {ready.data.current.period} →{" "}
                {openOption.day} {openOption.period}
              </dd>
            </div>

            <div>
              <dt>{openOption.kind === "swap" ? "Swaps with" : "Target slot"}</dt>
              <dd>
                {openOption.partner ? (
                  <>
                    {openOption.partner.subject} · {openOption.partner.target}
                    <br />
                    moves to {openOption.partner.moves_to.day}{" "}
                    {openOption.partner.moves_to.period}
                  </>
                ) : (
                  "free period — nothing is displaced"
                )}
              </dd>
            </div>

            <div>
              <dt>Impact</dt>
              <dd>
                overall {openOption.soft_delta >= 0 ? "+" : ""}
                {openOption.soft_delta.toFixed(2)} · soft score becomes{" "}
                {openOption.soft_after.toFixed(2)}
                <br />
                fairness {openOption.components.teacher_workload >= 0 ? "+" : ""}
                {(openOption.components.teacher_workload * 15).toFixed(2)}
              </dd>
            </div>
          </dl>

          {preview && (
            <p className="slotdetail__preview">
              Preview — nothing changed yet. Soft score would become{" "}
              {preview.soft_after.toFixed(2)} with {preview.hard_total} hard
              violations.
            </p>
          )}

          {editor.error && <p className="modal__error">{editor.error}</p>}

          <div className="slotdetail__actions">
            <button
              type="button"
              className="button button--small"
              onClick={() => editor.previewOption(openOption)}
              disabled={editor.busy}
            >
              Preview
            </button>
            <button
              type="button"
              className="button button--small button--apply"
              onClick={() => editor.applyOption(openOption)}
              disabled={editor.busy}
            >
              {editor.busy ? "Working…" : "Apply Change"}
            </button>
          </div>
        </aside>
        )}
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
