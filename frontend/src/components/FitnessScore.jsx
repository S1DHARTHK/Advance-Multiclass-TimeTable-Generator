/** Fitness score of the generated timetable, as reported by the GA. */

export default function FitnessScore({ fitness }) {
  const { score, maxScore, periodViolations, structuralViolations } = fitness;
  const percent = maxScore ? Math.max(0, Math.min(100, (score / maxScore) * 100)) : 0;
  const isPerfect = periodViolations === 0 && structuralViolations === 0;

  return (
    <section className="fitness" aria-label="Fitness score">
      <div className="fitness__head">
        <span className="fitness__label">Fitness score</span>
        <span className="fitness__value">
          {score.toFixed(2)}
          <span className="fitness__max"> / {maxScore.toFixed(2)}</span>
        </span>
      </div>

      <div
        className="fitness__bar"
        role="progressbar"
        aria-valuenow={Math.round(percent)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="fitness__fill" style={{ width: `${percent}%` }} />
      </div>

      <ul className="fitness__checks">
        <li className={periodViolations === 0 ? "ok" : "bad"}>
          {periodViolations === 0
            ? "Every subject has its required periods"
            : `${periodViolations} period count violation(s)`}
        </li>
        <li className={structuralViolations === 0 ? "ok" : "bad"}>
          {structuralViolations === 0
            ? "One subject per slot"
            : `${structuralViolations} slot violation(s)`}
        </li>
        {isPerfect && <li className="ok">All constraints satisfied</li>}
      </ul>
    </section>
  );
}
