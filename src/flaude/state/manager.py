"""Thin wrapper around file I/O for session state persistence.

All writes are atomic: write to <path>.tmp, then os.rename().
"""

from __future__ import annotations

import os
from pathlib import Path

from flaude.constants import SESSIONS_DIR
from flaude.state.models import SessionState


class StateManager:
    """Reads and writes session state files from disk."""

    def __init__(
        self,
        sessions_dir: Path | None = None,
    ) -> None:
        self.sessions_dir = sessions_dir or SESSIONS_DIR

    # -- helpers --

    def _session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _atomic_write(self, path: Path, data: str) -> None:
        """Write data to path atomically via a .tmp rename."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(data, encoding="utf-8")
        os.rename(tmp, path)

    # -- session CRUD --

    def save_session(self, state: SessionState) -> None:
        """Persist a SessionState to disk."""
        self._atomic_write(
            self._session_path(state.session_id),
            state.model_dump_json(indent=2),
        )

    def load_session(self, session_id: str) -> SessionState | None:
        """Load a single session. Returns None if missing or corrupt."""
        path = self._session_path(session_id)
        if not path.exists():
            return None
        try:
            return SessionState.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def load_all_sessions(self) -> dict[str, SessionState]:
        """Load every *.json in the sessions dir, keyed by session_id."""
        result: dict[str, SessionState] = {}
        if not self.sessions_dir.exists():
            return result
        for path in self.sessions_dir.glob("*.json"):
            try:
                state = SessionState.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
                result[state.session_id] = state
            except Exception:
                # Corrupt file — skip it, don't crash the whole load.
                continue
        return result

    def delete_session(self, session_id: str) -> None:
        """Remove a session state file. No-op if it doesn't exist."""
        path = self._session_path(session_id)
        path.unlink(missing_ok=True)
