"""Thin wrapper around file I/O for session state persistence.

All writes are atomic: write to <path>.tmp, then os.rename().
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from flaude.constants import DECISIONS_DIR, SESSIONS_DIR
from flaude.state.models import PendingPermission, SessionState


class StateManager:
    """Reads and writes session state files from disk."""

    def __init__(
        self,
        sessions_dir: Path | None = None,
        decisions_dir: Path | None = None,
    ) -> None:
        self.sessions_dir = sessions_dir or SESSIONS_DIR
        self.decisions_dir = decisions_dir or DECISIONS_DIR

    # -- helpers --

    def _session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _decision_path(self, session_id: str, request_id: str) -> Path:
        return self.decisions_dir / f"{session_id}_{request_id}.json"

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
        """Load a single session. Returns None if the file doesn't exist."""
        path = self._session_path(session_id)
        if not path.exists():
            return None
        return SessionState.model_validate_json(path.read_text(encoding="utf-8"))

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

    # -- pending permissions --

    def add_pending_permission(
        self,
        session_id: str,
        request_id: str,
        tool_name: str,
        tool_input: dict,
        rule_matched: str | None,
        timeout_at: datetime,
    ) -> None:
        """Read-modify-write: append a PendingPermission to session state."""
        state = self.load_session(session_id)
        if state is None:
            return
        state.pending_permissions.append(
            PendingPermission(
                request_id=request_id,
                tool_name=tool_name,
                tool_input=tool_input,
                rule_matched=rule_matched,
                created_at=datetime.now(),
                timeout_at=timeout_at,
            )
        )
        state.status = state.status  # preserve existing status; caller sets it
        self.save_session(state)

    def resolve_permission(self, session_id: str, request_id: str) -> None:
        """Remove a pending permission by request_id."""
        state = self.load_session(session_id)
        if state is None:
            return
        state.pending_permissions = [
            p for p in state.pending_permissions if p.request_id != request_id
        ]
        self.save_session(state)

    # -- decisions --

    def write_decision(self, session_id: str, request_id: str, decision: dict) -> None:
        """Write a decision file for the hook to pick up."""
        self._atomic_write(
            self._decision_path(session_id, request_id),
            json.dumps(decision),
        )

    def read_decision(self, session_id: str, request_id: str) -> dict | None:
        """Read and delete a decision file. Returns None if not found."""
        path = self._decision_path(session_id, request_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        path.unlink()
        return data
