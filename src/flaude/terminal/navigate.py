"""Navigate to a Claude Code session's terminal tab/window via AppleScript."""

import subprocess
from pathlib import Path


def navigate_to_session(terminal: str | None, cwd: str) -> bool:
    """Switch to the terminal tab whose working directory matches cwd.

    Returns True if navigation succeeded, False otherwise.
    """
    if not terminal or not cwd:
        return False

    script = _build_script(terminal, cwd)
    if not script:
        return False

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "true" in result.stdout.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _build_script(terminal: str, cwd: str) -> str | None:
    basename = Path(cwd).name

    if terminal == "iTerm2":
        return f"""
        tell application "iTerm2"
            activate
            repeat with w in windows
                repeat with t in tabs of w
                    repeat with s in sessions of t
                        try
                            set sessionDir to variable named "user.currentDirectory" of s
                            if sessionDir contains "{cwd}" then
                                select t
                                tell w to select
                                return "true"
                            end if
                        end try
                    end repeat
                end repeat
            end repeat
        end tell
        return "false"
        """

    if terminal == "Ghostty":
        return f"""
        tell application "System Events"
            tell process "Ghostty"
                set allWindows to every window
                repeat with w in allWindows
                    if name of w contains "{basename}" then
                        perform action "AXRaise" of w
                        tell application "Ghostty" to activate
                        return "true"
                    end if
                end repeat
            end tell
        end tell
        return "false"
        """

    if terminal == "Terminal":
        return f"""
        tell application "Terminal"
            activate
            repeat with w in windows
                repeat with t in tabs of w
                    try
                        if custom title of t contains "{basename}" then
                            set selected tab of w to t
                            set index of w to 1
                            return "true"
                        end if
                    end try
                end repeat
            end repeat
        end tell
        return "false"
        """

    return None
