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
from flaude.git import get_git_info
from flaude.rules.engine import RulesEngine
from flaude.state.manager import StateManager
from flaude.hooks.teams import read_lead_session_id
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


def _get_usage_from_transcript(
    transcript_path: str | None,
    existing_custom_title: str | None = None,
) -> tuple[int, str | None, str | None]:
    """Read the latest token usage, model, and custom title from the transcript JSONL.

    Tokens and model are always read from the tail (last 10KB).
    Custom title: if *existing_custom_title* is None a full-file scan is done
    once; on subsequent calls the tail is checked for newer entries and the
    cached value is returned if none are found.
    """
    if not transcript_path:
        return 0, None, None
    try:
        path = Path(transcript_path)
        if not path.exists():
            return 0, None, None

        # Full-file scan only when no cached title yet
        custom_title = existing_custom_title
        if existing_custom_title is None:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if '"custom-title"' not in line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("type") == "custom-title":
                            custom_title = entry.get("customTitle") or None
                    except json.JSONDecodeError:
                        continue

        # Tail read for tokens, model, and title updates
        size = path.stat().st_size
        with open(path, "rb") as f:
            f.seek(max(0, size - 51200))
            tail = f.read().decode("utf-8", errors="ignore")
        if size > 51200:
            first_nl = tail.find("\n")
            if first_nl != -1:
                tail = tail[first_nl + 1 :]
        tokens, model = 0, None
        found_title_in_tail = False
        for line in reversed(tail.strip().splitlines()):
            try:
                # Check for custom-title updates in tail (re-renames)
                if not found_title_in_tail and '"custom-title"' in line:
                    entry = json.loads(line)
                    if entry.get("type") == "custom-title":
                        custom_title = entry.get("customTitle") or None
                        found_title_in_tail = True
                        continue
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
                    break
            except (json.JSONDecodeError, AttributeError):
                continue
    except (OSError, ValueError):
        return 0, None, None
    return tokens, model, custom_title


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
    # Backfill team fields (for sessions created before team support)
    if not state.team_name and event.get("teamName"):
        state.team_name = event["teamName"]
        state.agent_name = event.get("agentName")
        state.lead_session_id = read_lead_session_id(state.team_name)
    # Update custom_title if the event provides one — Claude Code sends it after /rename
    if event.get("customTitle"):
        state.custom_title = event["customTitle"]
    # Backfill git fields for sessions created before worktree support.
    # Use empty string sentinel to avoid re-calling git on non-repo dirs.
    if state.git_repo_root is None and state.cwd:
        repo_root, branch, is_wt = get_git_info(state.cwd)
        state.git_repo_root = repo_root or ""
        state.git_branch = branch
        state.git_is_worktree = is_wt
    return state


# ---------------------------------------------------------------------------
# Per-event handlers
# ---------------------------------------------------------------------------


def _handle_session_start(event: dict, sm: StateManager) -> None:
    session_id = event.get("session_id", "")
    now = utcnow()

    team_name = event.get("teamName")
    agent_name = event.get("agentName")
    lead_session_id = read_lead_session_id(team_name) if team_name else None

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
        team_name=team_name,
        agent_name=agent_name,
        lead_session_id=lead_session_id,
    )
    repo_root, branch, is_wt = get_git_info(state.cwd)
    state.git_repo_root = repo_root or ""
    state.git_branch = branch
    state.git_is_worktree = is_wt
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
    tokens, model, custom_title = _get_usage_from_transcript(
        state.transcript_path, existing_custom_title=state.custom_title
    )
    state.context_tokens = tokens
    if model:
        state.model = model
    if custom_title:
        state.custom_title = custom_title
    # Refresh branch in case user checked out a different branch during the turn
    if state.cwd:
        _, branch, _ = get_git_info(state.cwd)
        if branch:
            state.git_branch = branch
    sm.save_session(state)
    _log(state.session_id, "Stop", "idle")


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


def _handle_permission_request(event: dict, sm: StateManager) -> None:
    tool_name = event.get("tool_name", "")
    state = _load_or_create(event, sm)
    # Don't overwrite WAITING_ANSWER (AskUserQuestion) or PLAN (ExitPlanMode)
    if state.status not in (SessionStatus.WAITING_ANSWER, SessionStatus.PLAN):
        state.status = SessionStatus.WAITING_PERMISSION
    state.last_event = "PermissionRequest"
    state.last_event_at = utcnow()
    sm.save_session(state)
    _log(state.session_id, "PermissionRequest", tool_name)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Callable[[dict, StateManager], None]] = {
    "SessionStart": _handle_session_start,
    "PreToolUse": _handle_pre_tool_use,
    "PostToolUse": _handle_post_tool_use,
    "Stop": _handle_stop,
    "UserPromptSubmit": _handle_user_prompt_submit,
    "SubagentStop": _handle_subagent_stop,
    "PreCompact": _handle_pre_compact,
    "SessionEnd": _handle_session_end,
    "PermissionRequest": _handle_permission_request,
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
