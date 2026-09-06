"""
editor_server.py
----------------
A small HTTP front door for the timetable and the slot editor.

Standard library only - no framework, no database. It holds one SlotEditor
in memory, serves the current timetable, answers "where else could this
lesson go?", and applies a change only when asked to.

    GET  /api/health              is the service up, and what is loaded
    GET  /api/solution            the current timetable (class- and teacher-wise)
    POST /api/candidates          {teacher_id, day, period, limit}
    POST /api/preview             {change}   score it, change nothing
    POST /api/apply               {change}   commit it, then save

Nothing is written until /api/apply succeeds, and a change that would break
a hard constraint is refused there as well as ranked out of /api/candidates.

Run:  python editor_server.py
      python editor_server.py --port 8000
"""

from __future__ import annotations

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from slot_editor import load_editor
from version_history import VersionHistory

SOLUTION_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "timetable_solution.json"
)

# One editor, one lock: applies are serialised so two callers cannot both
# write from the same starting timetable.
STATE = {
    "editor": None,
    "history": None,
    "lock": threading.Lock(),
    "applied": 0,
}


def change_label(applied: dict) -> str:
    """Short, readable name for the version an edit produces."""
    lesson = applied.get("lesson") or {}
    move = applied.get("change", {})
    return "%s %s: %s %s to %s %s" % (
        lesson.get("subject", "Lesson"),
        lesson.get("target", ""),
        move.get("from", {}).get("day", ""),
        move.get("from", {}).get("period", ""),
        move.get("to", {}).get("day", ""),
        move.get("to", {}).get("period", ""),
    )


def save_solution(editor) -> None:
    with open(SOLUTION_PATH, "w", encoding="utf-8") as handle:
        json.dump(editor.solution(), handle, indent=2, ensure_ascii=False)


class Handler(BaseHTTPRequestHandler):
    server_version = "TimetableEditor/1.0"

    # ------------------------------------------------------------ plumbing

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # the UI is served from the Vite dev server on another port
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def log_message(self, fmt, *args):        # quieter console
        print("  %s %s" % (self.command, self.path))

    def do_OPTIONS(self):
        self._send(204, {})

    # -------------------------------------------------------------- routes

    def do_GET(self):
        editor = STATE["editor"]

        if self.path == "/api/health":
            return self._send(200, {
                "status": "ok",
                "classes": len(editor.problem.classes),
                "teachers": len(editor.problem.teachers),
                "hard_violations": editor.baseline.hard_total,
                "soft_total": round(editor.baseline.soft_total, 2),
                "changes_applied": STATE["applied"],
                "versions": len(STATE["history"].versions),
                "current_version": STATE["history"].current_id,
            })

        if self.path == "/api/solution":
            return self._send(200, editor.solution())

        if self.path == "/api/versions":
            return self._send(200, STATE["history"].to_dict())

        return self._send(404, {"error": "no such endpoint: %s" % self.path})

    def do_POST(self):
        editor = STATE["editor"]

        try:
            body = self._read_json()
        except ValueError as error:
            return self._send(400, {"error": "invalid JSON: %s" % error})

        try:
            if self.path == "/api/candidates":
                teacher_id = body.get("teacher_id")
                day = body.get("day")
                period = body.get("period")

                placements = editor.placements_at(teacher_id, day, period)
                if not placements:
                    return self._send(404, {
                        "error": "%s has no lesson at %s %s"
                                 % (teacher_id, day, period)
                    })

                # a clashing slot can hold more than one lesson; the caller
                # may name the one it means
                placement = placements[0]
                wanted = body.get("unit_id")
                if wanted:
                    for item in placements:
                        if editor.problem.units[item.unit_index].unit_id == wanted:
                            placement = item
                            break

                return self._send(200, editor.candidates(
                    placement, int(body.get("limit") or 5), teacher_id
                ))

            if self.path == "/api/preview":
                return self._send(200, editor.preview(body["change"]))

            if self.path == "/api/apply":
                with STATE["lock"]:
                    applied = editor.apply(body["change"])
                    # every edit becomes a version you can come back to
                    STATE["history"].record(change_label(applied),
                                            applied.get("change"))
                    save_solution(editor)
                    STATE["applied"] += 1

                return self._send(200, {
                    "applied": applied,
                    "report": {
                        "hard_total": editor.baseline.hard_total,
                        "soft_total": round(editor.baseline.soft_total, 2),
                    },
                    "solution": editor.solution(),
                    "history": STATE["history"].to_dict(),
                })

            if self.path == "/api/versions/restore":
                with STATE["lock"]:
                    version = STATE["history"].restore(int(body["version_id"]))
                    save_solution(editor)

                return self._send(200, {
                    "restored": version,
                    "report": {
                        "hard_total": editor.baseline.hard_total,
                        "soft_total": round(editor.baseline.soft_total, 2),
                    },
                    "solution": editor.solution(),
                    "history": STATE["history"].to_dict(),
                })

        except KeyError as error:
            return self._send(400, {"error": "missing field %s" % error})
        except ValueError as error:
            # includes "would break a hard constraint" and stale-change errors
            return self._send(409, {"error": str(error)})

        return self._send(404, {"error": "no such endpoint: %s" % self.path})


def main() -> int:
    parser = argparse.ArgumentParser(description="Timetable editor service")
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("PORT") or 8000))
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    print("Loading timetable...")
    STATE["editor"] = load_editor()
    editor = STATE["editor"]
    STATE["history"] = VersionHistory(editor)
    print("  %d classes, %d teachers, %d hard violations, soft %.2f"
          % (len(editor.problem.classes), len(editor.problem.teachers),
             editor.baseline.hard_total, editor.baseline.soft_total))

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("Editor service on http://%s:%d  (Ctrl+C to stop)"
          % (args.host, args.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
