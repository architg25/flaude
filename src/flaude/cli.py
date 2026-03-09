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
    HOOK_COMMAND_PYTHON,
    HOOK_TIMEOUT_DEFAULT,
    RULES_PATH,
    SESSIONS_DIR,
    STATE_DIR,
    DASHBOARD_PID,
    _HOOK_BINARY,
    atomic_write,
    ensure_dirs,
    get_model_limit,
    resolve_hook_command,
    utcnow,
)
from flaude.config import load_config, save_config
from flaude.formatting import format_token_count, format_uptime


# All hooks are non-blocking (monitor only)
HOOK_EVENTS = [
    "PreToolUse",
    "PostToolUse",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "SubagentStop",
    "PreCompact",
    "UserPromptSubmit",
    "PermissionRequest",
]


def _build_hook_entry(hook_command: str) -> dict:
    return {
        "matcher": "",
        "hooks": [
            {
                "type": "command",
                "command": hook_command,
                "timeout": HOOK_TIMEOUT_DEFAULT,
            }
        ],
    }


def _load_settings() -> dict:
    if CLAUDE_SETTINGS_PATH.exists():
        try:
            with open(CLAUDE_SETTINGS_PATH, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def _save_settings(settings: dict) -> None:
    import io

    buf = io.StringIO()
    json.dump(settings, buf, indent=2)
    buf.write("\n")
    atomic_write(CLAUDE_SETTINGS_PATH, buf.getvalue())


def _hooks_installed() -> bool:
    """Check if flaude hooks are registered in Claude settings."""
    settings = _load_settings()
    hooks = settings.get("hooks", {})
    for event_hooks in hooks.values():
        for entry in event_hooks:
            if _is_flaude_hook(entry):
                return True
    return False


def _is_flaude_hook(entry: dict) -> bool:
    """Check if a hook entry belongs to flaude (Rust binary or Python fallback)."""
    for hook in entry.get("hooks", []):
        cmd = hook.get("command", "")
        if "flaude.hooks.dispatcher" in cmd or "flaude-hook" in cmd:
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


_GIT_SSH_URL = "ssh://git@ghe.spotify.net/vibes/flaude.git"

_ARTIFACTORY_INDEX = "https://artifactory.spotify.net/artifactory/api/pypi/pypi/simple/"
_GIT_URL = "git+ssh://git@ghe.spotify.net/vibes/flaude.git"
_GIT_URL_OLD = "git+ssh://git@ghe.spotify.net/architg/flaude.git"


def _print_update_result(old_version: str) -> None:
    """Print update result by comparing old version to freshly installed one."""
    import subprocess

    # Use importlib.metadata to read the *installed* package version,
    # avoiding stale __version__ from editable/dev installs.
    new_version = subprocess.run(
        [
            sys.executable,
            "-c",
            "from importlib.metadata import version; print(version('flaude'))",
        ],
        capture_output=True,
        text=True,
    ).stdout.strip()

    if new_version == old_version:
        print(f"Already up to date ({old_version}).")
    else:
        print(f"Updated: {old_version} -> {new_version}")
    print()


def _run_init() -> None:
    """Run hook init after update.

    Must use subprocess so the freshly-installed code is loaded — otherwise
    HOOK_COMMAND (resolved at import time) would still point to the old
    dispatcher (e.g. Python fallback when Rust binary wasn't yet installed).
    """
    import subprocess

    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.argv = ['flaude', 'init']; from flaude.cli import main; main()",
        ]
    )


def cmd_update(args: argparse.Namespace) -> None:
    """Self-update flaude from Artifactory or Git remote."""
    import shutil
    import subprocess

    from flaude import __version__

    allow_dev = getattr(args, "dev", False)

    print(f"Current version: {__version__}")
    print("Updating flaude...")

    # Strategy 1: uv from Artifactory (fastest — pre-built wheel)
    uv = shutil.which("uv")
    if uv:
        cmd = [
            uv,
            "pip",
            "install",
            "--python",
            sys.executable,
            "--upgrade",
            "flaude",
            "--index-url",
            _ARTIFACTORY_INDEX,
        ]
        if not allow_dev:
            cmd.append("--prerelease=disallow")
        result = subprocess.run(cmd)
        if result.returncode == 0:
            _print_update_result(__version__)
            _run_init()
            return

    # Strategy 2: pip from Artifactory
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "flaude",
        "--index-url",
        _ARTIFACTORY_INDEX,
    ]
    if not allow_dev:
        cmd.append("--no-pre")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        _print_update_result(__version__)
        _run_init()
        return

    # Strategy 3: pip from git+ssh (fallback)
    for url in (_GIT_URL, _GIT_URL_OLD):
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--force-reinstall", url]
        )
        if result.returncode == 0:
            _print_update_result(__version__)
            _run_init()
            return

    print(
        "\nUpdate failed from all sources.\n"
        "Try manually:\n\n"
        f"  pip install flaude --index-url {_ARTIFACTORY_INDEX}\n"
        f"  pip install {_GIT_URL}\n",
        file=sys.stderr,
    )
    sys.exit(1)


def _try_compile_rust() -> bool:
    """Compile the Rust dispatcher if missing. Returns True if binary is available."""
    if _HOOK_BINARY.exists() and os.access(_HOOK_BINARY, os.X_OK):
        return True

    cargo = shutil.which("cargo")
    if not cargo:
        return False

    import subprocess
    import tempfile

    print("Rust dispatcher not found — compiling from source...")
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp) / "repo"
        install_dir = Path(tmp) / "out"

        # Shallow clone just enough to build
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", _GIT_SSH_URL, str(repo_dir)],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            print("  Failed to clone source — using Python fallback.")
            return False

        try:
            subprocess.run(
                [
                    "cargo",
                    "install",
                    "--path",
                    str(repo_dir / "rust"),
                    "--root",
                    str(install_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            print("  Rust compilation failed — using Python fallback.")
            return False

        built = install_dir / "bin" / "flaude-hook"
        if not built.exists():
            print("  Binary not found after build — using Python fallback.")
            return False

        _HOOK_BINARY.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(built), str(_HOOK_BINARY))
        _HOOK_BINARY.chmod(0o755)
        print("  Compiled native Rust dispatcher.")
        return True


def cmd_init(args: argparse.Namespace) -> None:
    """Install flaude hooks into Claude Code settings."""
    settings = _load_settings()
    hooks = settings.setdefault("hooks", {})

    if args.dry_run:
        hook_cmd = resolve_hook_command()
        dispatcher = "Rust" if hook_cmd != HOOK_COMMAND_PYTHON else "Python"
        print(f"Dry run — would install hooks ({dispatcher} dispatcher):")
        print(f"  Hook command: {hook_cmd}")
        for event in HOOK_EVENTS:
            print(f"  {event} (timeout: {HOOK_TIMEOUT_DEFAULT}s)")
        print(f"\nSettings file: {CLAUDE_SETTINGS_PATH}")
        return

    # Compile Rust dispatcher if not already present
    _try_compile_rust()
    hook_cmd = resolve_hook_command()

    backup = _backup_settings()
    if backup:
        print(f"Backed up settings to {backup}")

    for event in HOOK_EVENTS:
        event_hooks = hooks.setdefault(event, [])
        # Remove existing flaude hooks
        event_hooks[:] = [h for h in event_hooks if not _is_flaude_hook(h)]
        # Add new flaude hook
        event_hooks.append(_build_hook_entry(hook_cmd))

    _save_settings(settings)
    ensure_dirs()
    _copy_default_rules()

    if hook_cmd != HOOK_COMMAND_PYTHON:
        print("flaude hooks installed (native Rust dispatcher).")
    else:
        print("flaude hooks installed (Python dispatcher).")
    print(f"  Hook: {hook_cmd}")
    print(f"  Settings: {CLAUDE_SETTINGS_PATH}")
    print(f"  State dir: {SESSIONS_DIR.parent}")
    print(f"\nRun 'flaude' to start the dashboard.")

    # Non-critical: check for updates
    try:
        from flaude.version_check import check_for_update

        config = load_config()
        result = check_for_update(config)
        if result:
            save_config(config)
            current, remote = result
            print(f"\n  Update available ({current} -> {remote}). Run: flaude update")
    except Exception:
        pass  # version check is best-effort


def cmd_uninstall(args: argparse.Namespace) -> None:
    """Remove flaude hooks from Claude Code settings."""
    if not CLAUDE_SETTINGS_PATH.exists():
        print("No settings file found. Nothing to uninstall.")
        return

    settings = _load_settings()
    hooks = settings.get("hooks", {})

    if args.dry_run:
        print("Dry run — would remove flaude hooks (Rust and Python) from:")
        for event in HOOK_EVENTS:
            if event in hooks:
                for entry in hooks[event]:
                    if _is_flaude_hook(entry):
                        cmd = entry.get("hooks", [{}])[0].get("command", "")
                        print(f"  {event}: {cmd}")
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
        config_dir = Path("~/.config/flaude").expanduser()
        if config_dir.exists():
            shutil.rmtree(config_dir)
            print(f"Removed {config_dir}")
        if STATE_DIR.exists():
            shutil.rmtree(STATE_DIR)
            print(f"Removed {STATE_DIR}")

        # Remove Rust binary if present (editable installs leave it behind)
        from flaude.constants import _HOOK_BINARY

        if _HOOK_BINARY.exists():
            _HOOK_BINARY.unlink()
            print(f"Removed {_HOOK_BINARY}")

        # Clean Rust build artifacts if in a source checkout
        rust_target = Path(__file__).parent.parent.parent / "rust" / "target"
        if rust_target.exists():
            shutil.rmtree(rust_target)
            print(f"Removed {rust_target}")

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

    # uninstall the package itself
    import subprocess

    print()
    uv = shutil.which("uv")
    if uv and "uv/tools/" in sys.executable:
        subprocess.run([uv, "tool", "uninstall", "flaude"])
    else:
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "flaude"])


def cmd_run(args: argparse.Namespace) -> None:
    """Launch the TUI dashboard."""
    if not _hooks_installed():
        print("First run detected — registering hooks...")
        cmd_init(argparse.Namespace(dry_run=False))
        print()

    ensure_dirs()

    # Overwrite process name from "python3.13" to "Flaude".
    # iTerm2 shows this as the tab title automatically.
    try:
        from setproctitle import setproctitle

        setproctitle("Flaude")
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


def _format_context(tokens: int, model: str | None) -> str:
    if not tokens:
        return "-"
    limit = get_model_limit(model)
    pct = int(tokens / limit * 100)
    return f"{format_token_count(tokens)} ({pct}%)"


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
        uptime = format_uptime(utcnow(), state.started_at)
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
            "  flaude update       Self-update from Git remote\n"
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

    # update
    p_update = sub.add_parser("update", help="Self-update flaude")
    p_update.add_argument(
        "--dev", action="store_true", help="Include dev/pre-release versions"
    )

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "uninstall": cmd_uninstall,
        "status": cmd_status,
        "update": cmd_update,
    }

    if args.command is None:
        cmd_run(args)
    elif args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
