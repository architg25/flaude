"""Stale session detection and orphan cleanup."""

from datetime import timedelta

from flaude.constants import STALE_SESSION_TIMEOUT, utcnow
from flaude.state.manager import StateManager
from flaude.state.models import SessionStatus


def cleanup_stale_sessions(mgr: StateManager | None = None) -> int:
    """Mark stale sessions as ended. Returns count of cleaned sessions."""
    mgr = mgr or StateManager()
    sessions = mgr.load_all_sessions()
    cutoff = utcnow() - timedelta(seconds=STALE_SESSION_TIMEOUT)
    cleaned = 0

    for sid, state in sessions.items():
        if state.status == SessionStatus.ENDED:
            continue

        if state.last_event_at < cutoff:
            state.status = SessionStatus.ENDED
            mgr.save_session(state)
            cleaned += 1
            continue

        # Resolve timed-out permissions
        now = utcnow()
        expired = [p for p in state.pending_permissions if p.timeout_at < now]
        if expired:
            for p in expired:
                mgr.resolve_permission(sid, p.request_id)

    return cleaned
