"""Stale session detection and orphan cleanup."""

import subprocess
from datetime import timedelta

from flaude.constants import STALE_SESSION_TIMEOUT, utcnow
from flaude.state.manager import StateManager
from flaude.state.models import SessionStatus

# Sessions inactive for this many seconds get a process check
_PROCESS_CHECK_THRESHOLD = 30


def _session_has_process(cwd: str) -> bool:
    """Check if any claude process is running with the given cwd."""
    if not cwd:
        return False
    try:
        result = subprocess.run(
            ["lsof", "-d", "cwd", "-c", "claude", "-c", "node", "-Fn"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        cwd_normalized = cwd.rstrip("/")
        for line in result.stdout.strip().splitlines():
            if line.startswith("n") and line[1:].rstrip("/") == cwd_normalized:
                return True
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # If we can't check, assume alive to avoid false cleanup
        return True


def cleanup_stale_sessions(mgr: StateManager | None = None) -> int:
    """Mark stale sessions as ended. Returns count of cleaned sessions."""
    mgr = mgr or StateManager()
    sessions = mgr.load_all_sessions()
    now = utcnow()
    cutoff_stale = now - timedelta(seconds=STALE_SESSION_TIMEOUT)
    cutoff_check = now - timedelta(seconds=_PROCESS_CHECK_THRESHOLD)
    cleaned = 0

    for sid, state in sessions.items():
        if state.status == SessionStatus.ENDED:
            continue

        # Hard timeout: session hasn't reported anything in a long time
        if state.last_event_at < cutoff_stale:
            state.status = SessionStatus.ENDED
            mgr.save_session(state)
            cleaned += 1
            continue

        # Soft check: session inactive for 30s+ — verify process exists
        if state.last_event_at < cutoff_check:
            if not _session_has_process(state.cwd):
                mgr.delete_session(sid)
                cleaned += 1
                continue

        # Resolve timed-out permissions
        expired = [p for p in state.pending_permissions if p.timeout_at < now]
        if expired:
            for p in expired:
                mgr.resolve_permission(sid, p.request_id)

    return cleaned
