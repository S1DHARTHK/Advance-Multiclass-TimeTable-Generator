/**
 * Required vs scheduled periods for one class, subject by subject.
 */

export default function SubjectRequirements({ rows }) {
  const shortfall = rows.filter((row) => !row.ok).length;

  return (
    <section className="req">
      <header className="req__head">
        <h3 className="req__title">Subject Requirements</h3>
        <p className="req__meta">
          {shortfall === 0
            ? "All subjects have their required weekly periods"
            : `${shortfall} subject${shortfall === 1 ? "" : "s"} not correctly scheduled`}
        </p>
      </header>

      <div className="req__scroll">
        <table className="req__table">
          <thead>
            <tr>
              <th scope="col">Subject</th>
              <th scope="col">Required / week</th>
              <th scope="col">Scheduled</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.subject} className={row.ok ? "" : "req__row--bad"}>
                <td>
                  {row.subject}
                  {row.taughtInLanguageGroups && (
                    <span className="req__note"> (parallel language groups)</span>
                  )}
                </td>
                <td className="req__num">{row.required}</td>
                <td className="req__num">{row.scheduled}</td>
                <td>
                  {row.ok ? (
                    <span className="pill pill--ok">✓ Complete</span>
                  ) : (
                    <span className="pill pill--bad">
                      {row.scheduled < row.required
                        ? `Short by ${row.required - row.scheduled}`
                        : `Over by ${row.scheduled - row.required}`}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
