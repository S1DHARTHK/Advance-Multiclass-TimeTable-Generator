"""
version_history.py
------------------
The timetable's edit history.

Every applied edit records a new version, and any version can be made
current again at any time - backwards or forwards.

This is deliberately NOT an undo stack:

  * nothing is ever discarded;
  * restoring an older version does not delete the newer ones, it just
    moves the "current" marker, so you can go straight back forward again;
  * editing while an older version is current appends a new version at the
    end rather than truncating the ones after it.

So the history is a flat, append-only log of timetable states, and the
list the UI shows is the whole of it.

Snapshots are held in memory for the life of the service; the current
timetable itself is what gets written to disk on every change.
"""

from __future__ import annotations

from datetime import datetime


class VersionHistory:
    def __init__(self, editor, label: str = "Original generated timetable"):
        self.editor = editor
        self.versions: list = []
        self.current_id: int | None = None
        self.record(label)

    # ---------------------------------------------------------------- write

    def record(self, label: str, change: dict | None = None) -> dict:
        """Snapshot the editor's current timetable as a new version."""
        version = {
            "id": len(self.versions),
            "label": label,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "hard_total": self.editor.baseline.hard_total,
            "soft_total": round(self.editor.baseline.soft_total, 2),
            "change": change,
            # kept server-side only; the UI never needs the raw chromosome
            "genes": [list(slots) for slots in self.editor.genes],
        }
        self.versions.append(version)
        self.current_id = version["id"]
        return self.public(version)

    def restore(self, version_id: int) -> dict:
        """Make an existing version current again. Nothing is removed."""
        version = self.find(version_id)
        self.editor.set_genes(version["genes"])
        self.current_id = version["id"]
        return self.public(version)

    # ----------------------------------------------------------------- read

    def find(self, version_id: int) -> dict:
        for version in self.versions:
            if version["id"] == version_id:
                return version
        raise ValueError("no version with id %r" % version_id)

    @staticmethod
    def public(version: dict) -> dict:
        return {key: value for key, value in version.items() if key != "genes"}

    def to_dict(self) -> dict:
        return {
            "current_id": self.current_id,
            "versions": [self.public(version) for version in self.versions],
        }
