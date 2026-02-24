"""Discover pre-existing Claude sessions not yet tracked by flaude.

At TUI startup, scans ~/.claude/projects/*/*.jsonl for recently modified
transcripts, cross-references with running Claude processes and the
activity log, and creates bootstrap state files so they appear immediately
in the dashboard.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, UTC
from pathlib import Path

from flaude.constants import ACTIVITY_LOG, STALE_SESSION_TIMEOUT, utcnow
from flaude.state.cleanup import _get_active_cwds
from flaude.state.manager import StateManager
from flaude.state.models import SessionState, SessionStatus

_CLAUDE_PROJECTS_DIR = Path("~/.claude/projects").expanduser()


def _parse_activity_log() -> tuple[set[str], set[str]]:
    """Parse the activity log for ended and known session IDs.

    Returns (ended_sids, known_sids) as sets of short IDs (first 8 chars).
    A session is "ended" if the log has a `SessionEnd` event for it.
    A session is "known" if the log has any event for it.
    """
    ended: set[str] = set()
    known: set[str] = set()
    try:
        with open(ACTIVITY_LOG, "r", encoding="utf-8") as f:
            for line in f:
                # Format: "2026-02-28T16:18:07 [2ed3541f] SessionEnd"
                # The ] must be followed by a space and event name — not embedded
                # in tool output like: PreToolUse Bash "...SessionEnd..."
                bracket_start = line.find("[")
                bracket_end = (
                    line.find("]", bracket_start + 1) if bracket_start != -1 else -1
                )
                if bracket_start == -1 or bracket_end == -1:
                    continue
                sid = line[bracket_start + 1 : bracket_end]
                known.add(sid)
                rest = line[bracket_end + 1 :].lstrip()
                if rest.startswith("SessionEnd"):
                    ended.add(sid)
                elif rest.startswith("SessionStart"):
                    # Session was resumed — no longer ended
                    ended.discard(sid)
    except (OSError, UnicodeDecodeError):
        pass
    return ended, known


def scan_preexisting_sessions(mgr: StateManager) -> int:
    """Bootstrap state files for running Claude sessions flaude doesn't know about.

    Returns count of discovered sessions.
    """
    if not _CLAUDE_PROJECTS_DIR.exists():
        return 0

    active_cwds = _get_active_cwds()
    if not active_cwds:
        return 0

    # Parse activity log once: sessions that ended, and sessions we've seen at all
    ended_sids, known_sids = _parse_activity_log()

    cutoff = time.time() - STALE_SESSION_TIMEOUT
    discovered = 0

    for transcript in _CLAUDE_PROJECTS_DIR.glob("*/*.jsonl"):
        # Skip subagent transcripts (live under <session_id>/subagents/)
        if "subagents" in transcript.parts:
            continue

        # Skip old transcripts
        try:
            if transcript.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue

        session_id = transcript.stem
        short_id = session_id[:8]

        # Skip if this session ended (activity log has SessionEnd for it)
        if short_id in ended_sids:
            continue

        # Skip if hooks never saw this session (predates hook installation)
        if short_id not in known_sids:
            continue

        # Skip if we already track this session
        if mgr.load_session(session_id) is not None:
            continue

        # Read first line to get session metadata
        try:
            with open(transcript, "r", encoding="utf-8") as f:
                first_line = f.readline()
            entry = json.loads(first_line)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue

        cwd = entry.get("cwd", "")
        if not cwd or cwd.rstrip("/") not in active_cwds:
            continue

        # Parse started_at from transcript timestamp
        started_at = utcnow()
        ts = entry.get("timestamp")
        if ts:
            try:
                started_at = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(
                    tzinfo=None
                )
            except (ValueError, AttributeError):
                pass

        state = SessionState(
            session_id=session_id,
            status=SessionStatus.IDLE,
            cwd=cwd,
            transcript_path=str(transcript),
            started_at=started_at,
            last_event="Discovered",
            last_event_at=utcnow(),
        )
        mgr.save_session(state)
        discovered += 1

    return discovered
