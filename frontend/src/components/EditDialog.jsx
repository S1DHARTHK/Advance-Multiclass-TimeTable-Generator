/**
 * The complete ranked list of alternative slots.
 *
 * The grid already shows the options shaded in place; this is the full
 * table behind the "All options" button - same data, same shading, but
 * every candidate with its numbers side by side for comparison.
 *
 * Nothing is changed until Apply Change is pressed.
 */

import { useState } from "react";

import { optionKey, tintFor } from "./TeacherSchedule";

const COMPONENT_LABELS = {
  period_priority: "Period priority",
  class_teacher_first_period: "Class teacher P1",
  subject_distribution: "Subject spread",
  teacher_workload: "Workload fairness",
  gaps_and_blocks: "Gaps & blocks",
};

export default function EditDialog({ editor, onClose }) {
  const session = editor.session;
  const ready = session?.status === "ready" ? session : null;
  const [chosen, setChosen] = useState(null);

  const options = ready?.data.candidates ?? [];
  const scores = options.map((option) => option.fitness_delta);
  const best = Math.max(...scores, 0);
  const worst = Math.min(...scores, 0);
  const span = best - worst;

  const preview =
    chosen && editor.preview?.key === optionKey(chosen)
      ? editor.preview.data
      : null;

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label="All options">
      <div className="modal__box modal__box--wide">
        <header className="modal__head">
          <div>
            <h2 className="modal__title">All alternative slots</h2>
            {ready && (
              <p className="modal__sub">
                {ready.data.current.subject} · {ready.data.current.target} —
                currently {ready.data.current.day} {ready.data.current.period}
              </p>
            )}
          </div>
          <button type="button" className="modal__close" onClick={onClose}>
            Close
          </button>
        </header>

        <div className="modal__body">
          {session?.status === "loading" && (
            <p className="modal__note">Checking every slot in the week…</p>
          )}

          {session?.status === "error" && (
            <p className="modal__error">{session.error}</p>
          )}

          {ready && (
            <>
              <p className="modal__note">
                Checked {ready.data.considered} slots · {ready.data.rejected}{" "}
                ruled out by hard constraints or structure ·{" "}
                {options.length} valid. Timetable now:{" "}
                {ready.data.baseline.hard_total} violations, soft{" "}
                {ready.data.baseline.soft_total.toFixed(2)}.
              </p>

              {options.length === 0 ? (
                <p className="modal__note">
                  No alternative slot keeps every hard constraint satisfied.
                </p>
              ) : (
                <div className="optiontable__scroll">
                  <table className="optiontable">
                    <thead>
                      <tr>
                        <th scope="col">#</th>
                        <th scope="col">Slot</th>
                        <th scope="col">Type</th>
                        <th scope="col">Hard</th>
                        <th scope="col">Overall</th>
                        <th scope="col">Fairness</th>
                        <th scope="col">What happens</th>
                      </tr>
                    </thead>
                    <tbody>
                      {options.map((option, index) => {
                        const ratio =
                          span > 1e-9 ? (best - option.fitness_delta) / span : 0;
                        const active =
                          chosen && optionKey(chosen) === optionKey(option);

                        return (
                          <tr
                            key={optionKey(option)}
                            className={`optiontable__row ${active ? "is-active" : ""}`}
                            onClick={() => setChosen(option)}
                          >
                            <td>
                              <span
                                className="swatch"
                                style={tintFor(ratio)}
                                aria-hidden="true"
                              />
                              {index + 1}
                            </td>
                            <td className="optiontable__slot">
                              {option.day} {option.period}
                            </td>
                            <td>
                              <span className={`badge badge--${option.kind}`}>
                                {option.kind === "swap" ? "Swap" : "Move"}
                              </span>
                            </td>
                            <td>
                              <span className="badge badge--ok">✓</span>
                            </td>
                            <td
                              className={
                                option.soft_delta >= 0 ? "is-better" : "is-worse"
                              }
                            >
                              {option.soft_delta >= 0 ? "+" : ""}
                              {option.soft_delta.toFixed(2)}
                            </td>
                            <td
                              className={
                                option.components.teacher_workload >= 0
                                  ? "is-better"
                                  : "is-worse"
                              }
                            >
                              {option.components.teacher_workload >= 0 ? "+" : ""}
                              {(option.components.teacher_workload * 15).toFixed(2)}
                            </td>
                            <td className="optiontable__what">
                              {option.partner
                                ? `${option.partner.subject} → ${option.partner.moves_to.day} ${option.partner.moves_to.period}`
                                : "free period"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {preview && (
                <div className="preview">
                  <p className="preview__head">
                    Preview — nothing has been changed yet
                  </p>
                  <p className="preview__line">{preview.summary}</p>
                  <ul className="preview__grid">
                    {Object.entries(preview.components).map(([key, delta]) => (
                      <li key={key}>
                        <span>{COMPONENT_LABELS[key] ?? key}</span>
                        <strong className={delta >= 0 ? "is-better" : "is-worse"}>
                          {delta >= 0 ? "+" : ""}
                          {delta.toFixed(3)}
                        </strong>
                      </li>
                    ))}
                  </ul>
                  <p className="preview__line">
                    Soft score would become {preview.soft_after.toFixed(2)} with{" "}
                    {preview.hard_total} hard violations.
                  </p>
                </div>
              )}

              {editor.error && <p className="modal__error">{editor.error}</p>}
            </>
          )}
        </div>

        <footer className="modal__foot">
          <span className="modal__chosen">
            {chosen
              ? `Selected: ${chosen.day} ${chosen.period}`
              : "Select a row to preview or apply"}
          </span>
          <button
            type="button"
            className="button"
            onClick={() => editor.previewOption(chosen)}
            disabled={!chosen || editor.busy}
          >
            Preview
          </button>
          <button
            type="button"
            className="button button--apply"
            onClick={() => editor.applyOption(chosen)}
            disabled={!chosen || editor.busy}
          >
            {editor.busy ? "Working…" : "Apply Change"}
          </button>
        </footer>
      </div>
    </div>
  );
}
