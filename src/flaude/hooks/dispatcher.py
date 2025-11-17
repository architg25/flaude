"""Single entry point for all Claude Code hook events.

Claude Code invokes: python3 -m flaude.hooks.dispatcher
and pipes a JSON payload to stdin.  We route on hook_event_name,
update state, and (for PreToolUse) potentially block-and-poll for
dashboard approval.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from flaude.constants import (
    ACTIVITY_LOG,
    DASHBOARD_PID,
    DEFAULT_APPROVAL_TIMEOUT,
    NO_DASHBOARD_BEHAVIOR,
    POLL_INTERVAL,
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
# Blocking approval flow (PreToolUse → ask_dashboard)
# ---------------------------------------------------------------------------


def _handle_ask_dashboard(
    session_id: str,
    tool_name: str,
    tool_input: dict,
    rule_result,
    state_manager: StateManager,
) -> None:
    request_id = f"req_{uuid.uuid4().hex[:8]}"
    timeout = rule_result.timeout or DEFAULT_APPROVAL_TIMEOUT
    timeout_at = utcnow() + timedelta(seconds=timeout)

    # If no dashboard is running, fall back to configured behavior.
    if not DASHBOARD_PID.exists():
        behavior = NO_DASHBOARD_BEHAVIOR
        if behavior == "allow":
            _emit_decision("allow")
            return
        elif behavior == "deny":
            _emit_decision("deny")
            return
        else:  # "passthrough"
            sys.exit(0)

    # Register the pending permission so the TUI can display it.
    state_manager.add_pending_permission(
        session_id=session_id,
        request_id=request_id,
        tool_name=tool_name,
        tool_input=tool_input,
        rule_matched=rule_result.rule_name,
        timeout_at=timeout_at,
    )

    # Block and poll for a decision file from the dashboard.
    while utcnow() < timeout_at:
        result = state_manager.read_decision(session_id, request_id)
        if result is not None:
            state_manager.resolve_permission(session_id, request_id)
            _emit_decision(result["decision"])
            return
        time.sleep(POLL_INTERVAL)

    # Timeout reached — clean up and deny.
    state_manager.resolve_permission(session_id, request_id)
    _emit_decision("deny")


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
        started_at=now,
        last_event="SessionStart",
        last_event_at=now,
    )
    sm.save_session(state)
    _log(session_id, "SessionStart")


def _handle_pre_tool_use(event: dict, sm: StateManager) -> None:
    session_id = event.get("session_id", "")
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    now = utcnow()

    state = sm.load_session(session_id)
    if state is None:
        # Session state missing (e.g. hook installed mid-session). Bootstrap.
        state = SessionState(
            session_id=session_id,
            cwd=event.get("cwd", ""),
            started_at=now,
            last_event_at=now,
        )

    summary = _summarize_tool(tool_name, tool_input)
    state.last_tool = LastTool(name=tool_name, summary=summary, at=now)
    state.tool_stats[tool_name] = state.tool_stats.get(tool_name, 0) + 1
    state.last_event = "PreToolUse"
    state.last_event_at = now
    sm.save_session(state)

    # Evaluate rules
    engine = RulesEngine.load()
    result = engine.evaluate(tool_name, tool_input, state.cwd)

    _log(session_id, "PreToolUse", f'{tool_name} "{summary}"')

    if result.action == "allow":
        _emit_decision("allow")
    elif result.action == "deny":
        _emit_decision("deny")
    elif result.action == "ask_dashboard":
        _handle_ask_dashboard(session_id, tool_name, tool_input, result, sm)
    # "no_match" — fall through to Claude Code's own prompt
    sys.exit(0)


def _handle_post_tool_use(event: dict, sm: StateManager) -> None:
    session_id = event.get("session_id", "")
    tool_name = event.get("tool_name", "")
    now = utcnow()

    state = sm.load_session(session_id)
    if state is None:
        return
    state.last_event = "PostToolUse"
    state.last_event_at = now
    sm.save_session(state)
    _log(session_id, "PostToolUse", tool_name)


def _handle_stop(event: dict, sm: StateManager) -> None:
    session_id = event.get("session_id", "")

    state = sm.load_session(session_id)
    if state is None:
        return
    # Only go idle if we're not waiting on something interactive.
    if state.status not in (
        SessionStatus.WAITING_PERMISSION,
        SessionStatus.WAITING_ANSWER,
    ):
        state.status = SessionStatus.IDLE
    state.last_event = "Stop"
    state.last_event_at = utcnow()
    sm.save_session(state)
    _log(session_id, "Stop", "idle")


def _handle_notification(event: dict, sm: StateManager) -> None:
    session_id = event.get("session_id", "")
    message = event.get("message", "").lower()

    state = sm.load_session(session_id)
    if state is None:
        return

    if "permission" in message:
        state.status = SessionStatus.WAITING_PERMISSION
    elif any(kw in message for kw in ("question", "input", "answer")):
        state.status = SessionStatus.WAITING_ANSWER

    state.last_event = "Notification"
    state.last_event_at = utcnow()
    sm.save_session(state)
    _log(session_id, "Notification", _trunc(message, 60))


def _handle_user_prompt_submit(event: dict, sm: StateManager) -> None:
    session_id = event.get("session_id", "")

    state = sm.load_session(session_id)
    if state is None:
        return
    state.status = SessionStatus.WORKING
    state.last_event = "UserPromptSubmit"
    state.last_event_at = utcnow()
    sm.save_session(state)
    _log(session_id, "UserPromptSubmit")


def _handle_subagent_stop(event: dict, sm: StateManager) -> None:
    session_id = event.get("session_id", "")

    state = sm.load_session(session_id)
    if state is None:
        return
    state.subagent_count = max(0, state.subagent_count - 1)
    state.last_event = "SubagentStop"
    state.last_event_at = utcnow()
    sm.save_session(state)
    _log(session_id, "SubagentStop")


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
