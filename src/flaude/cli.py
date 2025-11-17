"""CLI entry point: flaude init, run, uninstall, status, approve, deny."""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from flaude.constants import (
    CLAUDE_SETTINGS_PATH,
    DECISIONS_DIR,
    HOOK_COMMAND,
    HOOK_TIMEOUT_DEFAULT,
    HOOK_TIMEOUT_PRETOOLUSE,
    RULES_PATH,
    SESSIONS_DIR,
    DASHBOARD_PID,
    ensure_dirs,
)


# Events and their hook timeout
HOOK_EVENTS = {
    "PreToolUse": HOOK_TIMEOUT_PRETOOLUSE,
    "PostToolUse": HOOK_TIMEOUT_DEFAULT,
    "SessionStart": HOOK_TIMEOUT_DEFAULT,
    "SessionEnd": HOOK_TIMEOUT_DEFAULT,
    "Stop": HOOK_TIMEOUT_DEFAULT,
    "Notification": HOOK_TIMEOUT_DEFAULT,
    "UserPromptSubmit": HOOK_TIMEOUT_DEFAULT,
}


def _build_hook_entry(timeout: int) -> dict:
    return {
        "matcher": "",
        "hooks": [
            {
                "type": "command",
                "command": HOOK_COMMAND,
                "timeout": timeout,
            }
        ],
    }


def _load_settings() -> dict:
    if CLAUDE_SETTINGS_PATH.exists():
        with open(CLAUDE_SETTINGS_PATH) as f:
            return json.load(f)
    return {}


def _save_settings(settings: dict) -> None:
    CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CLAUDE_SETTINGS_PATH.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    os.rename(tmp, CLAUDE_SETTINGS_PATH)


def _is_flaude_hook(entry: dict) -> bool:
    """Check if a hook entry belongs to flaude."""
    for hook in entry.get("hooks", []):
        if HOOK_COMMAND in hook.get("command", ""):
            return True
    return False


def _backup_settings() -> Path | None:
    if not CLAUDE_SETTINGS_PATH.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = CLAUDE_SETTINGS_PATH.with_name(f"settings.json.backup_{ts}")
    shutil.copy2(CLAUDE_SETTINGS_PATH, backup)
    return backup


def _copy_default_rules() -> None:
    """Copy default rules to ~/.config/flaude/rules.yaml if not present."""
    if RULES_PATH.exists():
        return
    default_rules = Path(__file__).parent / "rules" / "default.yaml"
    if not default_rules.exists():
        return
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(default_rules, RULES_PATH)


def cmd_init(args: argparse.Namespace) -> None:
    """Install flaude hooks into Claude Code settings."""
    settings = _load_settings()
    hooks = settings.setdefault("hooks", {})

    if args.dry_run:
        print("Dry run — would install hooks for events:")
        for event in HOOK_EVENTS:
            print(f"  {event} (timeout: {HOOK_EVENTS[event]}s)")
        print(f"\nSettings file: {CLAUDE_SETTINGS_PATH}")
        return

    backup = _backup_settings()
    if backup:
        print(f"Backed up settings to {backup}")

    for event, timeout in HOOK_EVENTS.items():
        event_hooks = hooks.setdefault(event, [])
        # Remove existing flaude hooks
        event_hooks[:] = [h for h in event_hooks if not _is_flaude_hook(h)]
        # Add new flaude hook
        event_hooks.append(_build_hook_entry(timeout))

    _save_settings(settings)
    ensure_dirs()
    _copy_default_rules()

    print("flaude hooks installed.")
    print(f"  Settings: {CLAUDE_SETTINGS_PATH}")
    print(f"  Rules: {RULES_PATH}")
    print(f"  State dir: {SESSIONS_DIR.parent}")
    print(f"\nRun 'flaude run' to start the dashboard.")


def cmd_uninstall(args: argparse.Namespace) -> None:
    """Remove flaude hooks from Claude Code settings."""
    if not CLAUDE_SETTINGS_PATH.exists():
        print("No settings file found. Nothing to uninstall.")
        return

    settings = _load_settings()
    hooks = settings.get("hooks", {})

    if args.dry_run:
        print("Dry run — would remove flaude hooks from:")
        for event in HOOK_EVENTS:
            if event in hooks:
                print(f"  {event}")
        return

    backup = _backup_settings()
    if backup:
        print(f"Backed up settings to {backup}")

    for event in HOOK_EVENTS:
        if event in hooks:
            hooks[event] = [h for h in hooks[event] if not _is_flaude_hook(h)]
            if not hooks[event]:
                del hooks[event]

    if not hooks:
        settings.pop("hooks", None)

    _save_settings(settings)
    print("flaude hooks removed.")

    if args.purge:
        if RULES_PATH.exists():
            RULES_PATH.unlink()
            print(f"Removed {RULES_PATH}")
        rules_dir = RULES_PATH.parent
        if rules_dir.exists() and not any(rules_dir.iterdir()):
            rules_dir.rmdir()


def cmd_run(args: argparse.Namespace) -> None:
    """Launch the TUI dashboard."""
    ensure_dirs()

    # Write PID file
    DASHBOARD_PID.write_text(str(os.getpid()))

    try:
        from flaude.tui.app import FlaudeApp

        app = FlaudeApp()
        app.run()
    finally:
        if DASHBOARD_PID.exists():
            DASHBOARD_PID.unlink(missing_ok=True)


def cmd_status(args: argparse.Namespace) -> None:
    """Quick non-TUI status table."""
    from flaude.state.manager import StateManager

    mgr = StateManager()
    sessions = mgr.load_all_sessions()

    if not sessions:
        print("No active sessions.")
        return

    dashboard_running = DASHBOARD_PID.exists()
    print(f"Dashboard: {'running' if dashboard_running else 'not running'}")
    print()

    fmt = "{:<8} {:<12} {:<30} {:<20} {:<6}"
    print(fmt.format("Status", "Session", "Project", "Last Tool", "Tools"))
    print("-" * 78)

    for sid, state in sorted(sessions.items(), key=lambda x: x[1].started_at):
        project = Path(state.cwd).name if state.cwd else "?"
        last_tool = state.last_tool.name if state.last_tool else "-"
        tool_count = sum(state.tool_stats.values())
        print(
            fmt.format(
                state.status.value[:8],
                sid[:12],
                project[:30],
                last_tool[:20],
                str(tool_count),
            )
        )

    pending = sum(len(s.pending_permissions) for s in sessions.values())
    if pending:
        print(f"\n{pending} pending permission(s)")


def cmd_approve(args: argparse.Namespace) -> None:
    """Approve a pending permission from CLI."""
    from flaude.state.manager import StateManager

    mgr = StateManager()
    session_id = _resolve_session_id(mgr, args.session)
    if not session_id:
        return

    request_id = args.request
    if not request_id:
        state = mgr.load_session(session_id)
        if not state or not state.pending_permissions:
            print(f"No pending permissions for session {session_id[:12]}")
            return
        request_id = state.pending_permissions[0].request_id

    mgr.write_decision(session_id, request_id, "allow")
    print(f"Approved {request_id} for session {session_id[:12]}")


def cmd_deny(args: argparse.Namespace) -> None:
    """Deny a pending permission from CLI."""
    from flaude.state.manager import StateManager

    mgr = StateManager()
    session_id = _resolve_session_id(mgr, args.session)
    if not session_id:
        return

    request_id = args.request
    if not request_id:
        state = mgr.load_session(session_id)
        if not state or not state.pending_permissions:
            print(f"No pending permissions for session {session_id[:12]}")
            return
        request_id = state.pending_permissions[0].request_id

    mgr.write_decision(session_id, request_id, "deny")
    print(f"Denied {request_id} for session {session_id[:12]}")


def _resolve_session_id(mgr, prefix: str) -> str | None:
    """Resolve a session ID prefix to a full session ID."""
    sessions = mgr.load_all_sessions()
    matches = [sid for sid in sessions if sid.startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) == 0:
        print(f"No session found matching '{prefix}'")
        return None
    print(f"Ambiguous prefix '{prefix}', matches: {', '.join(s[:12] for s in matches)}")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="flaude", description="Claude Code session manager"
    )
    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="Install flaude hooks")
    p_init.add_argument(
        "--dry-run", action="store_true", help="Preview without changes"
    )

    # uninstall
    p_uninst = sub.add_parser("uninstall", help="Remove flaude hooks")
    p_uninst.add_argument(
        "--dry-run", action="store_true", help="Preview without changes"
    )
    p_uninst.add_argument(
        "--purge", action="store_true", help="Also remove config files"
    )

    # run
    sub.add_parser("run", help="Launch TUI dashboard")

    # status
    sub.add_parser("status", help="Quick status check")

    # approve
    p_approve = sub.add_parser("approve", help="Approve a pending permission")
    p_approve.add_argument("session", help="Session ID or prefix")
    p_approve.add_argument(
        "request", nargs="?", help="Request ID (default: oldest pending)"
    )

    # deny
    p_deny = sub.add_parser("deny", help="Deny a pending permission")
    p_deny.add_argument("session", help="Session ID or prefix")
    p_deny.add_argument(
        "request", nargs="?", help="Request ID (default: oldest pending)"
    )

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "uninstall": cmd_uninstall,
        "run": cmd_run,
        "status": cmd_status,
        "approve": cmd_approve,
        "deny": cmd_deny,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
