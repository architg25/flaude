"""Thin wrapper around file I/O for session state persistence.

All writes are atomic: write to <path>.tmp, then os.rename().
"""

from __future__ import annotations

from pathlib import Path

from flaude.constants import SESSIONS_DIR, atomic_write
from flaude.state.models import SessionState


class StateManager:
    """Reads and writes session state files from disk."""

    def __init__(
        self,
        sessions_dir: Path | None = None,
    ) -> None:
        self.sessions_dir = sessions_dir or SESSIONS_DIR
        self._cache: dict[Path, tuple[float, SessionState]] = {}

    # -- helpers --

    def _session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    # -- session CRUD --

    def save_session(self, state: SessionState) -> None:
        """Persist a SessionState to disk."""
        atomic_write(
            self._session_path(state.session_id),
            state.model_dump_json(indent=2),
        )

    def load_session(self, session_id: str) -> SessionState | None:
        """Load a single session. Returns None if missing or corrupt."""
        path = self._session_path(session_id)
        try:
            return SessionState.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def load_all_sessions(self) -> dict[str, SessionState]:
        """Load every *.json in the sessions dir, keyed by session_id.

        Uses mtime-based caching to avoid re-reading unchanged files.
        """
        result: dict[str, SessionState] = {}
        if not self.sessions_dir.exists():
            return result
        current_paths: set[Path] = set()
        for path in self.sessions_dir.glob("*.json"):
            current_paths.add(path)
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            cached = self._cache.get(path)
            if cached and cached[0] == mtime:
                result[cached[1].session_id] = cached[1]
                continue
            try:
                state = SessionState.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
                self._cache[path] = (mtime, state)
                result[state.session_id] = state
            except Exception:
                continue
        # Evict deleted files from cache
        for stale in set(self._cache) - current_paths:
            del self._cache[stale]
        return result

    def delete_session(self, session_id: str) -> None:
        """Remove a session state file. No-op if it doesn't exist."""
        path = self._session_path(session_id)
        self._cache.pop(path, None)
        path.unlink(missing_ok=True)
