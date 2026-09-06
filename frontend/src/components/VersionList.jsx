/**
 * The timetable's version history, always on show beside the grid.
 *
 * Every applied edit adds a version. Clicking any of them switches the
 * whole timetable to that state - backwards or forwards - and nothing is
 * ever removed, so this is a list you can move around in freely rather
 * than a one-step undo.
 */

function shortTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function VersionList({ history, onRestore, busy, live }) {
  const versions = history?.versions ?? [];
  const currentId = history?.current_id ?? null;

  // newest first: the most recent edits are the ones you reach for
  const ordered = [...versions].reverse();

  return (
    <aside className="versions" aria-label="Timetable versions">
      <div className="versions__head">
        <h2 className="versions__title">Versions</h2>
        <span className="versions__count">
          {versions.length || "—"}
        </span>
      </div>

      {!live ? (
        <p className="versions__note">
          Start the editor service to record and switch versions.
        </p>
      ) : versions.length === 0 ? (
        <p className="versions__note">No versions yet.</p>
      ) : (
        <>
          <p className="versions__note">
            Click any version to switch to it. Nothing is deleted, so you can
            go back and forward freely.
          </p>

          <ol className="versions__list">
            {ordered.map((version) => {
              const isCurrent = version.id === currentId;

              return (
                <li key={version.id}>
                  <button
                    type="button"
                    className={`version ${isCurrent ? "is-current" : ""}`}
                    onClick={() => onRestore(version.id)}
                    disabled={busy || isCurrent}
                    aria-current={isCurrent ? "true" : undefined}
                  >
                    <span className="version__top">
                      <span className="version__id">v{version.id}</span>
                      {isCurrent && (
                        <span className="version__badge">Current</span>
                      )}
                      <span className="version__time">
                        {shortTime(version.created_at)}
                      </span>
                    </span>

                    <span className="version__label">{version.label}</span>

                    <span className="version__stats">
                      soft {version.soft_total.toFixed(2)}
                      {version.hard_total > 0 && (
                        <span className="version__bad">
                          {" "}
                          · {version.hard_total} violation
                          {version.hard_total === 1 ? "" : "s"}
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </>
      )}
    </aside>
  );
}
