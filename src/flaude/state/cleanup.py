"""Stale session detection and orphan cleanup."""

import calendar
import os
import subprocess
from datetime import timedelta

from flaude.constants import STALE_SESSION_TIMEOUT, session_activity_path, utcnow
from flaude.state.manager import StateManager
from flaude.state.models import SessionState, SessionStatus, WAITING_STATUSES

# WORKING sessions inactive for this many seconds get a process check
_PROCESS_CHECK_THRESHOLD = 30
# IDLE/NEW sessions get a longer grace period — they're legitimately
# waiting for user input, not orphaned
_IDLE_PROCESS_CHECK_THRESHOLD = 300


def _get_active_cwds() -> set[str] | None:
    """Get CWDs of all running claude/node processes in one call.

    Returns None when lsof fails — callers must skip process checks rather
    than treating failure as "no processes running".
    """
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
        return None


def _delete_with_cache(mgr: StateManager, sid: str) -> None:
    """Delete session state and its activity cache file."""
    mgr.delete_session(sid)
    try:
        session_activity_path(sid).unlink(missing_ok=True)
    except OSError:
        pass


def cleanup_stale_sessions(mgr: StateManager | None = None) -> int:
    """Delete stale sessions. Returns count of cleaned sessions."""
    mgr = mgr or StateManager()
    sessions = mgr.load_all_sessions()
    now = utcnow()
    cutoff_stale = now - timedelta(seconds=STALE_SESSION_TIMEOUT)
    cutoff_working = now - timedelta(seconds=_PROCESS_CHECK_THRESHOLD)
    cutoff_idle = now - timedelta(seconds=_IDLE_PROCESS_CHECK_THRESHOLD)
    cleaned = 0

    # Lazy-load active CWDs only when needed (at most once per cleanup cycle).
    # Uses a sentinel so we distinguish "haven't tried" from "lsof failed (None)".
    _UNSET = object()
    active_cwds: set[str] | None | object = _UNSET

    for sid, state in sessions.items():
        if state.status == SessionStatus.ENDED:
            _delete_with_cache(mgr, sid)
            cleaned += 1
            continue

        # Hard timeout: session hasn't reported anything in a long time
        if state.last_event_at < cutoff_stale:
            _delete_with_cache(mgr, sid)
            cleaned += 1
            continue

        # Pick threshold based on status — IDLE sessions get a longer grace
        # period since they're legitimately waiting for user input
        is_idle = state.status in (SessionStatus.IDLE, SessionStatus.NEW)
        cutoff = cutoff_idle if is_idle else cutoff_working

        # Soft check: verify process still exists
        if state.last_event_at < cutoff:
            if active_cwds is _UNSET:
                active_cwds = _get_active_cwds()
            # lsof failed — don't nuke sessions based on missing data
            if active_cwds is None:
                continue
            cwd_normalized = (state.cwd or "").rstrip("/")
            if not cwd_normalized or cwd_normalized not in active_cwds:
                _delete_with_cache(mgr, sid)
                cleaned += 1
                continue

    return cleaned


# Minimum age (seconds) before we check transcript for staleness
_WAITING_MIN_AGE = 5
# Transcript must be modified at least this many seconds after last_event_at
_TRANSCRIPT_BUFFER = 2


def correct_stale_waiting(mgr: StateManager, sessions: dict[str, SessionState]) -> int:
    """Fix waiting states that weren't cleared by hooks.

    When a user declines a permission or plan, Claude Code may not fire
    PostToolUse/Stop events, leaving the session stuck in a waiting state.
    We detect this by comparing transcript mtime to last_event_at — if the
    transcript advanced, the session has moved on.

    Returns count of corrected sessions.
    """
    now = utcnow()
    corrected = 0
    for state in sessions.values():
        if state.status not in WAITING_STATUSES:
            continue
        if not state.transcript_path:
            continue
        age = (now - state.last_event_at).total_seconds()
        if age < _WAITING_MIN_AGE:
            continue
        try:
            mtime = os.path.getmtime(state.transcript_path)
        except OSError:
            continue
        event_ts = calendar.timegm(state.last_event_at.timetuple())
        if mtime > event_ts + _TRANSCRIPT_BUFFER:
            state.status = SessionStatus.WORKING
            state.last_event = "StaleWaitingCorrected"
            state.last_event_at = now
            mgr.save_session(state)
            corrected += 1
    return corrected
