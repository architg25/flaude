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
from collections.abc import Callable
from pathlib import Path

from flaude.constants import (
    ACTIVITY_LOG,
    ensure_dirs,
    utcnow,
)
from flaude.rules.engine import RulesEngine
from flaude.state.manager import StateManager
from flaude.state.models import LastTool, SessionState, SessionStatus
from flaude.tools import summarize_tool, trunc


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


def _detect_tty() -> str | None:
    """Detect the TTY by walking up the process tree from our parent.

    The hook's fds are all piped (no controlling terminal), but the parent
    process (Claude Code) runs on a real TTY. We read it via ps.
    """
    import subprocess

    pid = os.getppid()
    for _ in range(5):
        if pid <= 1:
            break
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "tty=,ppid="],
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (subprocess.TimeoutExpired, OSError):
            break
        parts = result.stdout.strip().split()
        if not parts:
            break
        tty = parts[0]
        if tty and tty != "??":
            return f"/dev/{tty}"
        if len(parts) >= 2:
            try:
                pid = int(parts[1])
            except ValueError:
                break
        else:
            break
    return None


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
# Token usage from transcript
# ---------------------------------------------------------------------------


def _get_usage_from_transcript(transcript_path: str | None) -> tuple[int, str | None]:
    """Read the latest token usage and model from the transcript JSONL."""
    if not transcript_path:
        return 0, None
    try:
        path = Path(transcript_path)
        if not path.exists():
            return 0, None
        # Read last 10KB to find the most recent usage entry
        size = path.stat().st_size
        with open(path, "rb") as f:
            f.seek(max(0, size - 10240))
            tail = f.read().decode("utf-8", errors="ignore")
        # Discard partial first line when we seeked to mid-file
        if size > 10240:
            first_nl = tail.find("\n")
            if first_nl != -1:
                tail = tail[first_nl + 1 :]
        # Search backwards for the latest usage
        for line in reversed(tail.strip().splitlines()):
            try:
                entry = json.loads(line)
                msg = entry.get("message", {})
                usage = msg.get("usage")
                if usage:
                    tokens = (
                        usage.get("cache_read_input_tokens", 0)
                        + usage.get("input_tokens", 0)
                        + usage.get("cache_creation_input_tokens", 0)
                    )
                    model = msg.get("model")
                    return tokens, model
            except (json.JSONDecodeError, AttributeError):
                continue
    except (OSError, ValueError):
        pass
    return 0, None


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
            tty=_detect_tty(),
            started_at=now,
            last_event_at=now,
        )
    # Backfill missing fields from event data
    if not state.transcript_path and event.get("transcript_path"):
        state.transcript_path = event["transcript_path"]
    if event.get("cwd"):
        state.cwd = event["cwd"]
    if not state.terminal:
        state.terminal = _detect_terminal_from_env()
    if not state.tty:
        state.tty = _detect_tty()
    # Always update permission_mode — it can change during a session
    if event.get("permission_mode"):
        state.permission_mode = event["permission_mode"]
    return state


# ---------------------------------------------------------------------------
# Per-event handlers
# ---------------------------------------------------------------------------


def _handle_session_start(event: dict, sm: StateManager) -> None:
    session_id = event.get("session_id", "")
    now = utcnow()
    state = SessionState(
        session_id=session_id,
        status=SessionStatus.NEW,
        cwd=event.get("cwd", ""),
        permission_mode=event.get("permission_mode", "default"),
        transcript_path=event.get("transcript_path"),
        terminal=_detect_terminal_from_env(),
        tty=_detect_tty(),
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

    summary = summarize_tool(tool_name, tool_input)
    state.last_tool = LastTool(name=tool_name, summary=summary, at=now)
    state.tool_stats[tool_name] = state.tool_stats.get(tool_name, 0) + 1
    state.status = SessionStatus.WORKING
    state.last_event = "PreToolUse"
    state.last_event_at = now

    if tool_name == "ExitPlanMode":
        state.pending_question = tool_input
        state.status = SessionStatus.PLAN
    elif tool_name == "AskUserQuestion":
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
        _log(
            state.session_id, "DENY", f"{tool_name} blocked by rule: {result.rule_name}"
        )
        _emit_decision("deny")


def _handle_post_tool_use(event: dict, sm: StateManager) -> None:
    tool_name = event.get("tool_name", "")
    state = _load_or_create(event, sm)
    state.last_event = "PostToolUse"
    state.last_event_at = utcnow()
    state.pending_question = None
    if state.status in (
        SessionStatus.WAITING_ANSWER,
        SessionStatus.PLAN,
        SessionStatus.WAITING_PERMISSION,
    ):
        state.status = SessionStatus.WORKING
    tokens, model = _get_usage_from_transcript(state.transcript_path)
    state.context_tokens = tokens
    if model:
        state.model = model
    sm.save_session(state)
    _log(state.session_id, "PostToolUse", tool_name)


def _handle_stop(event: dict, sm: StateManager) -> None:
    state = _load_or_create(event, sm)
    state.status = SessionStatus.IDLE
    state.pending_question = None
    if state.turn_started_at:
        state.last_turn_duration = (utcnow() - state.turn_started_at).total_seconds()
    state.turn_started_at = None
    state.last_event = "Stop"
    state.last_event_at = utcnow()
    sm.save_session(state)
    _log(state.session_id, "Stop", "idle")


def _handle_notification(event: dict, sm: StateManager) -> None:
    message = event.get("message", "").lower()
    state = _load_or_create(event, sm)

    if "permission" in message:
        state.status = SessionStatus.WAITING_PERMISSION
    elif "needs your attention" in message and state.status != SessionStatus.PLAN:
        state.status = SessionStatus.WAITING_ANSWER

    state.last_event = "Notification"
    state.last_event_at = utcnow()
    sm.save_session(state)
    _log(state.session_id, "Notification", trunc(message, 60))


def _handle_user_prompt_submit(event: dict, sm: StateManager) -> None:
    state = _load_or_create(event, sm)
    prompt = event.get("user_prompt", "")
    state.status = SessionStatus.WORKING
    state.turn_started_at = utcnow()
    state.last_prompt = prompt[:200] if prompt else state.last_prompt
    state.pending_question = None
    state.last_event = "UserPromptSubmit"
    state.last_event_at = utcnow()
    sm.save_session(state)
    _log(state.session_id, "UserPrompt", trunc(prompt, 80) if prompt else "")


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

_HANDLERS: dict[str, Callable[[dict, StateManager], None]] = {
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
    except Exception as e:
        # A hook crash must NEVER block Claude Code. Log and exit clean.
        _log("", "ERROR", str(e))
