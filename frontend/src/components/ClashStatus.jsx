/**
 * Hard-constraint status for the whole timetable.
 *
 * Hard violations decide whether the timetable is usable at all, so they
 * lead. Soft scores are shown underneath, clearly marked as quality
 * preferences that do not make a timetable invalid.
 */

import { useState } from "react";

import { VIOLATION_HINTS, VIOLATION_LABELS } from "../validation";

export default function ClashStatus({ validation, softReport }) {
  const [showDetails, setShowDetails] = useState(false);
  const clean = validation.total === 0;

  const present = Object.entries(validation.counts).filter(
    ([, count]) => count > 0
  );

  return (
    <section className={`status ${clean ? "status--ok" : "status--bad"}`}>
      <div className="status__head">
        <p className="status__headline">
          {clean ? "✓ No Clashes Detected" : `✕ ${validation.total} hard-constraint violation${validation.total === 1 ? "" : "s"}`}
        </p>
        {!clean && (
          <button
            type="button"
            className="status__toggle"
            onClick={() => setShowDetails((value) => !value)}
          >
            {showDetails ? "Hide details" : "View details"}
          </button>
        )}
      </div>

      {clean ? (
        <p className="status__note">
          Every class, teacher, availability and weekly-period rule is
          satisfied.
        </p>
      ) : (
        <ul className="status__counts">
          {present.map(([type, count]) => (
            <li key={type}>
              <strong>{count}</strong> {VIOLATION_LABELS[type]}
              <span className="status__hint"> — {VIOLATION_HINTS[type]}</span>
            </li>
          ))}
        </ul>
      )}

      {!clean && showDetails && (
        <ol className="status__list">
          {validation.violations.map((violation, index) => (
            <li key={index}>
              <span className="tag">{VIOLATION_LABELS[violation.type]}</span>{" "}
              {violation.message}
            </li>
          ))}
        </ol>
      )}

      {softReport?.total != null && (
        <p className="status__soft">
          Soft score {softReport.total.toFixed(2)} / {softReport.max.toFixed(0)}{" "}
          — scheduling quality (period priority, spread, workload). Separate
          from the hard constraints above; it never makes a timetable invalid.
        </p>
      )}
    </section>
  );
}
