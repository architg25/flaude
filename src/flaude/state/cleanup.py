"""Stale session detection and orphan cleanup."""

import subprocess
from datetime import timedelta

from flaude.constants import STALE_SESSION_TIMEOUT, utcnow
from flaude.state.manager import StateManager
from flaude.state.models import SessionStatus

# Sessions inactive for this many seconds get a process check
_PROCESS_CHECK_THRESHOLD = 30


def _get_active_cwds() -> set[str]:
    """Get CWDs of all running claude/node processes in one call."""
    try:
        result = subprocess.run(
            ["lsof", "-d", "cwd", "-c", "claude", "-c", "node", "-Fn"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        cwds = set()
        for line in result.stdout.strip().splitlines():
            if line.startswith("n"):
                cwds.add(line[1:].rstrip("/"))
        return cwds
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return set()


def cleanup_stale_sessions(mgr: StateManager | None = None) -> int:
    """Delete stale sessions. Returns count of cleaned sessions."""
    mgr = mgr or StateManager()
    sessions = mgr.load_all_sessions()
    now = utcnow()
    cutoff_stale = now - timedelta(seconds=STALE_SESSION_TIMEOUT)
    cutoff_check = now - timedelta(seconds=_PROCESS_CHECK_THRESHOLD)
    cleaned = 0

    # Lazy-load active CWDs only when needed (at most once per cleanup cycle)
    active_cwds: set[str] | None = None

    for sid, state in sessions.items():
        if state.status == SessionStatus.ENDED:
            continue

        # Hard timeout: session hasn't reported anything in a long time
        if state.last_event_at < cutoff_stale:
            mgr.delete_session(sid)
            cleaned += 1
            continue

        # Soft check: session inactive for 30s+ — verify process exists
        if state.last_event_at < cutoff_check:
            if active_cwds is None:
                active_cwds = _get_active_cwds()
            cwd_normalized = (state.cwd or "").rstrip("/")
            if not cwd_normalized or cwd_normalized not in active_cwds:
                mgr.delete_session(sid)
                cleaned += 1
                continue

    return cleaned
