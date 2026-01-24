"""Single entry point for all Claude Code hook events.

Claude Code invokes: python3 -m flaude.hooks.dispatcher
and pipes a JSON payload to stdin. We route on hook_event_name
and update session state. This is purely observational — flaude
does not block or gate permissions. Users approve in their
Claude terminal as normal.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from flaude.constants import (
    ACTIVITY_LOG,
    ensure_dirs,
    utcnow,
)
from flaude.rules.engine import RulesEngine
from flaude.state.manager import StateManager
from flaude.state.models import LastTool, SessionState, SessionStatus


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _log(session_id: str, event: str, detail: str = "") -> None:
    """Append one line to the activity log. Best-effort, never raises."""
    try:
        ts = utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        sid = session_id[:8] if session_id else "????????"
        parts = [ts, f"[{sid}]", event]
        if detail:
            parts.append(detail)
        line = " ".join(parts) + "\n"
        with open(ACTIVITY_LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass  # logging must never break the hook


# ---------------------------------------------------------------------------
# Tool-input summarization
# ---------------------------------------------------------------------------

_SUMMARIZERS: dict[str, object] = {
    "Bash": lambda inp: _trunc(inp.get("command", ""), 80),
    "Edit": lambda inp: _basename(inp.get("file_path", "")),
    "Write": lambda inp: _basename(inp.get("file_path", "")),
    "Read": lambda inp: _basename(inp.get("file_path", "")),
    "Grep": lambda inp: _trunc(inp.get("pattern", ""), 40),
    "Glob": lambda inp: inp.get("pattern", ""),
    "Task": lambda inp: _trunc(inp.get("prompt", ""), 60),
    "WebFetch": lambda inp: _trunc(inp.get("url", ""), 60),
}


def _trunc(s: str, n: int) -> str:
    return s[:n] + ("..." if len(s) > n else "")


def _basename(path: str) -> str:
    return Path(path).name if path else ""


def _summarize_tool(tool_name: str, tool_input: dict) -> str:
    fn = _SUMMARIZERS.get(tool_name)
    if fn:
        return fn(tool_input)
    return tool_name


# ---------------------------------------------------------------------------
# Permission output helpers
# ---------------------------------------------------------------------------


def _emit_decision(decision: str) -> None:
    """Write permission JSON to stdout and exit."""
    json.dump(
        {"hookSpecificOutput": {"permissionDecision": decision}},
        sys.stdout,
    )
    sys.exit(0)


# ---------------------------------------------------------------------------
# Terminal detection (runs inside the Claude session's terminal)
# ---------------------------------------------------------------------------

_TERM_PROGRAM_MAP = {
    "iTerm.app": "iTerm2",
    "ghostty": "Ghostty",
    "Apple_Terminal": "Terminal",
    "WarpTerminal": "Warp",
}


def _detect_terminal_from_env() -> str | None:
    """Detect terminal from env vars set by the terminal emulator."""
    term = os.environ.get("TERM_PROGRAM", "")
    if term in _TERM_PROGRAM_MAP:
        return _TERM_PROGRAM_MAP[term]
    # JetBrains integrated terminal sets TERMINAL_EMULATOR=JetBrains-JediTerm
    if "JetBrains" in os.environ.get("TERMINAL_EMULATOR", ""):
        return "IntelliJ"
    return None


# ---------------------------------------------------------------------------
# Session loading helper
# ---------------------------------------------------------------------------


def _load_or_create(event: dict, sm: StateManager) -> SessionState:
    """Load session state, creating if missing, and backfill fields from event."""
    session_id = event.get("session_id", "")
    state = sm.load_session(session_id)
    if state is None:
        now = utcnow()
        state = SessionState(
            session_id=session_id,
            cwd=event.get("cwd", ""),
            transcript_path=event.get("transcript_path"),
            terminal=_detect_terminal_from_env(),
            started_at=now,
            last_event_at=now,
        )
    # Backfill any missing fields from event data
    if not state.transcript_path and event.get("transcript_path"):
        state.transcript_path = event["transcript_path"]
    if not state.cwd and event.get("cwd"):
        state.cwd = event["cwd"]
    if not state.terminal:
        state.terminal = _detect_terminal_from_env()
    return state


# ---------------------------------------------------------------------------
# Per-event handlers
# ---------------------------------------------------------------------------


def _handle_session_start(event: dict, sm: StateManager) -> None:
    session_id = event.get("session_id", "")
    now = utcnow()
    state = SessionState(
        session_id=session_id,
        cwd=event.get("cwd", ""),
        permission_mode=event.get("permission_mode", "default"),
        transcript_path=event.get("transcript_path"),
        terminal=_detect_terminal_from_env(),
        started_at=now,
        last_event="SessionStart",
        last_event_at=now,
    )
    sm.save_session(state)
    _log(session_id, "SessionStart")


def _handle_pre_tool_use(event: dict, sm: StateManager) -> None:
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    now = utcnow()

    state = _load_or_create(event, sm)

    summary = _summarize_tool(tool_name, tool_input)
    state.last_tool = LastTool(name=tool_name, summary=summary, at=now)
    state.tool_stats[tool_name] = state.tool_stats.get(tool_name, 0) + 1
    state.status = SessionStatus.WORKING
    state.last_event = "PreToolUse"
    state.last_event_at = now

    if tool_name in ("AskUserQuestion", "ExitPlanMode"):
        state.pending_question = tool_input
        state.status = SessionStatus.WAITING_ANSWER
    else:
        state.pending_question = None

    sm.save_session(state)

    _log(state.session_id, "PreToolUse", f'{tool_name} "{summary}"')

    # Only hard-deny dangerous commands. Everything else passes through
    # to Claude Code's normal permission flow.
    engine = RulesEngine.load()
    result = engine.evaluate(tool_name, tool_input, state.cwd)

    if result.action == "deny":
        _emit_decision("deny")


def _handle_post_tool_use(event: dict, sm: StateManager) -> None:
    tool_name = event.get("tool_name", "")
    state = _load_or_create(event, sm)
    state.last_event = "PostToolUse"
    state.last_event_at = utcnow()
    sm.save_session(state)
    _log(state.session_id, "PostToolUse", tool_name)


def _handle_stop(event: dict, sm: StateManager) -> None:
    state = _load_or_create(event, sm)
    state.status = SessionStatus.IDLE
    state.last_event = "Stop"
    state.last_event_at = utcnow()
    sm.save_session(state)
    _log(state.session_id, "Stop", "idle")


def _handle_notification(event: dict, sm: StateManager) -> None:
    message = event.get("message", "").lower()
    state = _load_or_create(event, sm)

    if "permission" in message:
        state.status = SessionStatus.WAITING_PERMISSION
    elif "needs your attention" in message:
        state.status = SessionStatus.WAITING_ANSWER

    state.last_event = "Notification"
    state.last_event_at = utcnow()
    sm.save_session(state)
    _log(state.session_id, "Notification", _trunc(message, 60))


def _handle_user_prompt_submit(event: dict, sm: StateManager) -> None:
    state = _load_or_create(event, sm)
    prompt = event.get("user_prompt", "")
    state.status = SessionStatus.WORKING
    state.last_prompt = prompt[:200] if prompt else state.last_prompt
    state.pending_question = None
    state.last_event = "UserPromptSubmit"
    state.last_event_at = utcnow()
    sm.save_session(state)
    _log(state.session_id, "UserPrompt", _trunc(prompt, 80) if prompt else "")


def _handle_subagent_stop(event: dict, sm: StateManager) -> None:
    state = _load_or_create(event, sm)
    state.subagent_count = max(0, state.subagent_count - 1)
    state.last_event = "SubagentStop"
    state.last_event_at = utcnow()
    sm.save_session(state)
    _log(state.session_id, "SubagentStop")


def _handle_pre_compact(event: dict, sm: StateManager) -> None:
    session_id = event.get("session_id", "")
    _log(session_id, "PreCompact")


def _handle_session_end(event: dict, sm: StateManager) -> None:
    session_id = event.get("session_id", "")
    sm.delete_session(session_id)
    _log(session_id, "SessionEnd")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, object] = {
    "SessionStart": _handle_session_start,
    "PreToolUse": _handle_pre_tool_use,
    "PostToolUse": _handle_post_tool_use,
    "Stop": _handle_stop,
    "Notification": _handle_notification,
    "UserPromptSubmit": _handle_user_prompt_submit,
    "SubagentStop": _handle_subagent_stop,
    "PreCompact": _handle_pre_compact,
    "SessionEnd": _handle_session_end,
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    ensure_dirs()
    event = json.load(sys.stdin)
    event_name = event.get("hook_event_name", "")
    handler = _HANDLERS.get(event_name)
    if handler is not None:
        sm = StateManager()
        handler(event, sm)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # A hook crash must NEVER block Claude Code. Swallow and exit clean.
        pass
