"""Launch a new Claude Code session in a terminal tab."""

import subprocess

from flaude.terminal.detect import JETBRAINS_IDES


def launch_session(terminal: str | None, cwd: str) -> bool:
    """Open a new terminal tab and run claude in the given directory.

    Returns True if the tab was opened successfully.
    """
    if not terminal or not cwd:
        return False

    script = _build_launch_script(terminal, cwd)
    if not script:
        return False

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _build_launch_script(terminal: str, cwd: str) -> str | None:
    cmd = f"cd {cwd} && claude"

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

    if terminal == "Ghostty":
        # No tab creation API — open new window
        return f"""
        tell application "Ghostty" to activate
        tell application "System Events"
            tell process "Ghostty"
                keystroke "n" using command down
            end tell
        end tell
        delay 0.5
        tell application "System Events"
            tell process "Ghostty"
                keystroke "{cmd}"
                key code 36
            end tell
        end tell
        """

    if terminal == "Warp":
        # No tab API — open new window via Cmd+N, type command
        return f"""
        tell application "Warp" to activate
        tell application "System Events"
            tell process "Warp"
                keystroke "t" using command down
            end tell
        end tell
        delay 0.5
        tell application "System Events"
            tell process "Warp"
                keystroke "{cmd}"
                key code 36
            end tell
        end tell
        """

    if terminal == "IntelliJ":
        # Can't launch terminal tabs in JetBrains programmatically
        return None

    return None
