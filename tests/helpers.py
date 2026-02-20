"""Shared test helpers (importable by test modules)."""

from datetime import datetime, timezone

from flaude.state.models import SessionState


def make_state(session_id: str = "sess-1", **overrides) -> SessionState:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    defaults = dict(
        session_id=session_id,
        started_at=now,
        last_event_at=now,
    )
    defaults.update(overrides)
    return SessionState(**defaults)
