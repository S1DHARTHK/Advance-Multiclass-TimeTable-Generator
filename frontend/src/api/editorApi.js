/**
 * Client for the timetable editor service (editor_server.py).
 *
 * Requests go to /api, which the Vite dev server proxies to the Python
 * service. Point VITE_EDITOR_API somewhere else to talk to it directly.
 *
 * Every rule the service applies - hard constraints and soft scores alike -
 * comes from the same GA code that built the timetable. Nothing about
 * scheduling rules is decided here.
 */

const BASE = import.meta.env.VITE_EDITOR_API ?? "/api";

async function request(path, body) {
  const response = await fetch(`${BASE}${path}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });

  let data = {};
  try {
    data = await response.json();
  } catch {
    data = {};
  }

  if (!response.ok) {
    // the service explains refusals (e.g. a change that breaks a constraint)
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return data;
}

export const editorApi = {
  health: () => request("/health"),
  solution: () => request("/solution"),

  /** Ranked alternatives for the lesson this teacher has in that slot. */
  candidates: ({ teacherId, day, period, unitId, limit = 5 }) =>
    request("/candidates", {
      teacher_id: teacherId,
      day,
      period,
      unit_id: unitId,
      limit,
    }),

  /** Score a change without touching the timetable. */
  preview: (change) => request("/preview", { change }),

  /** Commit a change. Refused server-side if it breaks a hard constraint. */
  apply: (change) => request("/apply", { change }),
};
