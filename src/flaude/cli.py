"""CLI entry point: flaude init, run, uninstall, status."""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from flaude.constants import (
    CLAUDE_SETTINGS_PATH,
    HOOK_COMMAND,
    HOOK_TIMEOUT_DEFAULT,
    RULES_PATH,
    SESSIONS_DIR,
    DASHBOARD_PID,
    ensure_dirs,
)


# All hooks are non-blocking (monitor only)
HOOK_EVENTS = [
    "PreToolUse",
    "PostToolUse",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "SubagentStop",
    "PreCompact",
    "Notification",
    "UserPromptSubmit",
]


def _build_hook_entry() -> dict:
    return {
        "matcher": "",
        "hooks": [
            {
                "type": "command",
                "command": HOOK_COMMAND,
                "timeout": HOOK_TIMEOUT_DEFAULT,
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
            print(f"  {event} (timeout: {HOOK_TIMEOUT_DEFAULT}s)")
        print(f"\nSettings file: {CLAUDE_SETTINGS_PATH}")
        return

    backup = _backup_settings()
    if backup:
        print(f"Backed up settings to {backup}")

    for event in HOOK_EVENTS:
        event_hooks = hooks.setdefault(event, [])
        # Remove existing flaude hooks
        event_hooks[:] = [h for h in event_hooks if not _is_flaude_hook(h)]
        # Add new flaude hook
        event_hooks.append(_build_hook_entry())

    _save_settings(settings)
    ensure_dirs()
    _copy_default_rules()

    print("flaude hooks installed.")
    print(f"  Settings: {CLAUDE_SETTINGS_PATH}")
    print(f"  Rules: {RULES_PATH}")
    print(f"  State dir: {SESSIONS_DIR.parent}")
    print(f"\nRun 'flaude' to start the dashboard.")


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
        import shutil as _shutil

        config_dir = Path(os.path.expanduser("~/.config/flaude"))
        if config_dir.exists():
            _shutil.rmtree(config_dir)
            print(f"Removed {config_dir}")
        if STATE_DIR.exists():
            _shutil.rmtree(STATE_DIR)
            print(f"Removed {STATE_DIR}")

        # Check for env vars the user may have set
        env_vars = [
            "FLAUDE_STATE_DIR",
            "FLAUDE_CONFIG_PATH",
            "FLAUDE_RULES_PATH",
            "FLAUDE_STALE_SESSION_TIMEOUT",
            "FLAUDE_TUI_REFRESH_INTERVAL",
            "FLAUDE_TERMINAL",
        ]
        set_vars = [v for v in env_vars if os.environ.get(v)]
        if set_vars:
            print("\nThe following environment variables are still set in your shell:")
            for v in set_vars:
                print(f"  unset {v}")
            print("Add the above to your shell profile to fully clean up.")

    # pip uninstall
    import subprocess

    print()
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "flaude"])


def cmd_run(args: argparse.Namespace) -> None:
    """Launch the TUI dashboard."""
    ensure_dirs()

    # Overwrite process name from "python3.13" to "flaude".
    # iTerm2 shows this as the tab title automatically.
    try:
        from setproctitle import setproctitle

        setproctitle("flaude")
    except ImportError:
        pass

    # Write PID file
    DASHBOARD_PID.write_text(str(os.getpid()))

    try:
        from flaude.tui.app import FlaudeApp

        app = FlaudeApp()
        app.run()
    finally:
        if DASHBOARD_PID.exists():
            DASHBOARD_PID.unlink(missing_ok=True)


def _format_uptime(started_at: datetime) -> str:
    delta = datetime.now() - started_at
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m{secs % 60}s"
    hrs = mins // 60
    return f"{hrs}h{mins % 60}m"


def _format_context(tokens: int, model: str | None) -> str:
    if not tokens:
        return "-"
    model_limits = {"opus": 1_000_000, "sonnet": 200_000, "haiku": 200_000}
    limit = 200_000
    if model:
        for key, val in model_limits.items():
            if key in model:
                limit = val
                break
    pct = int(tokens / limit * 100)
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M ({pct}%)"
    if tokens >= 1_000:
        return f"{tokens // 1_000}K ({pct}%)"
    return f"{tokens} ({pct}%)"


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

    fmt = "{:<12} {:<10} {:<20} {:<12} {:<10} {:<14} {:<8}"
    print(
        fmt.format(
            "Status", "Session", "Project", "Terminal", "Mode", "Context", "Uptime"
        )
    )
    print("-" * 88)

    for sid, state in sorted(sessions.items(), key=lambda x: x[1].started_at):
        project = Path(state.cwd).name if state.cwd else "?"
        terminal = state.terminal or "-"
        mode = state.permission_mode or "default"
        context = _format_context(state.context_tokens, state.model)
        uptime = _format_uptime(state.started_at)
        print(
            fmt.format(
                state.status.value[:12],
                sid[:10],
                project[:20],
                terminal[:12],
                mode[:10],
                context[:14],
                uptime,
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="flaude",
        description="Claude Code session manager — TUI dashboard for monitoring multiple concurrent sessions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  flaude              Launch the dashboard\n"
            "  flaude init         Install hooks into Claude Code\n"
            "  flaude status       Quick status table (no TUI)\n"
        ),
    )
    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser(
        "init", help="Install flaude hooks into ~/.claude/settings.json"
    )
    p_init.add_argument(
        "--dry-run", action="store_true", help="Preview changes without writing"
    )

    # uninstall
    p_uninst = sub.add_parser(
        "uninstall", help="Remove flaude hooks from Claude Code settings"
    )
    p_uninst.add_argument(
        "--dry-run", action="store_true", help="Preview changes without writing"
    )
    p_uninst.add_argument(
        "--purge", action="store_true", help="Also remove ~/.config/flaude/"
    )

    # status
    sub.add_parser("status", help="Quick status table without launching the TUI")

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "uninstall": cmd_uninstall,
        "status": cmd_status,
    }

    if args.command is None:
        cmd_run(args)
    elif args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
