/**
 * "Where else could this lesson go?"
 *
 * Shows the lesson currently in the chosen slot and the best alternatives
 * the editor service found. Every option was already checked against the
 * full hard-constraint set server-side; the numbers shown come from the
 * same fitness function the timetable was generated with.
 *
 * Nothing is changed until Apply Change is pressed.
 */

import { useEffect, useState } from "react";

import { editorApi } from "../api/editorApi";

const COMPONENT_LABELS = {
  period_priority: "Period priority",
  class_teacher_first_period: "Class teacher P1",
  subject_distribution: "Subject spread",
  teacher_workload: "Workload fairness",
  gaps_and_blocks: "Gaps & blocks",
};

function Impact({ value, scale }) {
  const width = scale ? Math.min(100, (Math.abs(value) / scale) * 100) : 0;
  const better = value >= 0;

  return (
    <span className="impact">
      <span className="impact__track">
        <span
          className={`impact__fill ${better ? "is-better" : "is-worse"}`}
          style={{ width: `${Math.max(width, 3)}%` }}
        />
      </span>
      <span className={`impact__value ${better ? "is-better" : "is-worse"}`}>
        {value >= 0 ? "+" : ""}
        {value.toFixed(2)}
      </span>
    </span>
  );
}

export default function EditDialog({ teacherId, day, period, onClose, onApplied }) {
  const [state, setState] = useState({ status: "loading", data: null, error: null });
  const [chosen, setChosen] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    editorApi
      .candidates({ teacherId, day, period })
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data, error: null });
      })
      .catch((err) => {
        if (!cancelled)
          setState({ status: "error", data: null, error: err.message });
      });

    return () => {
      cancelled = true;
    };
  }, [teacherId, day, period]);

  const data = state.data;
  const options = data?.candidates ?? [];
  const scale = Math.max(
    0.01,
    ...options.map((option) => Math.abs(option.soft_delta))
  );

  async function handlePreview() {
    if (!chosen) return;
    setBusy(true);
    setError(null);
    try {
      setPreview(await editorApi.preview(chosen.change));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleApply() {
    if (!chosen) return;
    setBusy(true);
    setError(null);
    try {
      const result = await editorApi.apply(chosen.change);
      onApplied(result);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label="Edit lesson">
      <div className="modal__box">
        <header className="modal__head">
          <div>
            <h2 className="modal__title">Edit lesson</h2>
            {data && (
              <p className="modal__sub">
                {data.current.subject} · {data.current.target} — currently{" "}
                {data.current.day} {data.current.period}
              </p>
            )}
          </div>
          <button type="button" className="modal__close" onClick={onClose}>
            Close
          </button>
        </header>

        <div className="modal__body">
          {state.status === "loading" && (
            <p className="modal__note">Checking every slot in the week…</p>
          )}

          {state.status === "error" && (
            <p className="modal__error">{state.error}</p>
          )}

          {state.status === "ready" && (
            <>
              <p className="modal__note">
                Checked {data.considered} slots · {data.rejected} ruled out by
                hard constraints or structure · showing the best{" "}
                {options.length}. Timetable now: {data.baseline.hard_total}{" "}
                violations, soft {data.baseline.soft_total.toFixed(2)}.
              </p>

              {options.length === 0 ? (
                <p className="modal__note">
                  No alternative slot keeps every hard constraint satisfied.
                </p>
              ) : (
                <ul className="options">
                  {options.map((option, index) => {
                    const id = `${option.day}-${option.period}-${index}`;
                    const active = chosen === option;

                    return (
                      <li key={id}>
                        <label
                          className={`option ${active ? "is-active" : ""}`}
                        >
                          <input
                            type="radio"
                            name="slot-option"
                            className="option__radio"
                            checked={active}
                            onChange={() => {
                              setChosen(option);
                              setPreview(null);
                              setError(null);
                            }}
                          />

                          <span className="option__main">
                            <span className="option__top">
                              <strong className="option__slot">
                                {option.day} {option.period}
                              </strong>
                              <span
                                className={`badge badge--${option.kind}`}
                              >
                                {option.kind === "swap" ? "Swap" : "Move"}
                              </span>
                              <span className="badge badge--ok">
                                ✓ No clashes
                              </span>
                            </span>

                            <span className="option__summary">
                              {option.summary}
                            </span>

                            <span className="option__metrics">
                              <span className="option__metric">
                                Overall
                                <Impact value={option.soft_delta} scale={scale} />
                              </span>
                              <span className="option__metric">
                                Fairness
                                <Impact
                                  value={option.components.teacher_workload * 15}
                                  scale={scale}
                                />
                              </span>
                            </span>
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
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

              {error && <p className="modal__error">{error}</p>}
            </>
          )}
        </div>

        <footer className="modal__foot">
          <button
            type="button"
            className="button"
            onClick={handlePreview}
            disabled={!chosen || busy}
          >
            Preview
          </button>
          <button
            type="button"
            className="button button--apply"
            onClick={handleApply}
            disabled={!chosen || busy}
          >
            {busy ? "Working…" : "Apply Change"}
          </button>
          <button type="button" className="button" onClick={onClose}>
            Cancel
          </button>
        </footer>
      </div>
    </div>
  );
}
