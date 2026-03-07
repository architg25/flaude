"""Launch a new Claude Code session in a terminal tab."""

import subprocess

from flaude.terminal.navigate import escape_applescript


# Terminals without a native scripting API — use clipboard paste + Enter.
# Maps terminal name → (process name, new-tab key, modifier, new-tab delay, paste delay).
_GENERIC_TERMINALS = {
    "Ghostty": ("Ghostty", "t", "command down", 1.5, 0.5),
    "Warp": ("Warp", "t", "command down", 0.8, 0.3),
}


def launch_session(terminal: str | None, cwd: str, command: str | None = None) -> bool:
    """Open a new terminal tab and run a command.

    If *command* is None, defaults to ``cd <cwd> && claude``.
    Returns True if the tab was opened successfully.
    """
    if not terminal or not cwd:
        return False

    script = _build_launch_script(terminal, cwd, command=command)
    if not script:
        return False

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _build_launch_script(
    terminal: str, cwd: str, command: str | None = None
) -> str | None:
    cmd = escape_applescript(command or f"cd {cwd} && claude")

    if terminal == "iTerm2":
        return f"""
        tell application "iTerm2"
            activate
            tell current window
                create tab with default profile
                tell current session
                    write text "{cmd}"
                end tell
            end tell
        end tell
        """

    if terminal == "Terminal":
        return f"""
        tell application "Terminal"
            activate
            do script "{cmd}"
        end tell
        """

    if terminal in _GENERIC_TERMINALS:
        return _build_generic_launch(terminal, cwd, command)

    if terminal == "IntelliJ":
        return None

    # Unknown terminal — try generic clipboard approach with Cmd+T
    return _build_generic_launch(terminal, cwd, command)


def _build_generic_launch(terminal: str, cwd: str, command: str | None = None) -> str:
    """Clipboard paste + Enter for terminals without a scripting API."""
    process_name, key, modifier, tab_delay, paste_delay = _GENERIC_TERMINALS.get(
        terminal, (terminal, "t", "command down", 1.0, 0.5)
    )
    raw_cmd = command or f"cd {cwd} && claude"
    quoted = raw_cmd.replace("\\", "\\\\").replace("'", "'\\''")
    return f"""
    set prevClip to the clipboard
    do shell script "printf %s '{quoted}' | /usr/bin/pbcopy"
    tell application "{process_name}" to activate
    delay 0.5
    tell application "System Events"
        tell process "{process_name}"
            keystroke "{key}" using {modifier}
        end tell
    end tell
    delay {tab_delay}
    tell application "System Events"
        tell process "{process_name}"
            keystroke "v" using command down
        end tell
    end tell
    delay {paste_delay}
    tell application "System Events"
        tell process "{process_name}"
            key code 36
        end tell
    end tell
    delay 0.2
    do shell script "printf %s " & quoted form of prevClip & " | /usr/bin/pbcopy"
    """
