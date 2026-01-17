"""Navigate to a Claude Code session's terminal tab/window."""

import subprocess
from pathlib import Path

from flaude.terminal.detect import JETBRAINS_IDES


def navigate_to_session(terminal: str | None, cwd: str) -> bool:
    """Switch to the terminal tab whose working directory matches cwd.

    Returns True if navigation succeeded, False otherwise.
    """
    if not terminal or not cwd:
        return False

    try:
        if terminal == "iTerm2":
            return _navigate_iterm2(cwd)
        script = _build_script(terminal, cwd)
        if not script:
            return False
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "true" in result.stdout.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _navigate_iterm2(cwd: str) -> bool:
    """Navigate to an iTerm2 tab by matching tty → cwd.

    1. AppleScript: collect all session ttys with window/tab indices
    2. Python: for each tty, resolve cwd via lsof
    3. AppleScript: select the matching tab
    """
    # Step 1: Get all session ttys with their window/tab indices
    list_script = """
    tell application "iTerm2"
        set output to ""
        set wIdx to 0
        repeat with w in windows
            set wIdx to wIdx + 1
            set tIdx to 0
            repeat with t in tabs of w
                set tIdx to tIdx + 1
                repeat with s in sessions of t
                    set sessionTTY to tty of s
                    set output to output & sessionTTY & "|" & wIdx & "|" & tIdx & linefeed
                end repeat
            end repeat
        end repeat
        return output
    end tell
    """
    result = subprocess.run(
        ["osascript", "-e", list_script],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return False

    # Step 2: For each tty, resolve the foreground process cwd
    for line in result.stdout.strip().splitlines():
        parts = line.strip().split("|")
        if len(parts) != 3:
            continue
        tty, win_idx, tab_idx = parts[0], parts[1], parts[2]

        resolved_cwd = _get_cwd_for_tty(tty)
        if resolved_cwd and _cwds_match(resolved_cwd, cwd):
            # Step 3: Select this tab and bring window to front
            select_script = f"""
            tell application "iTerm2"
                set w to window {win_idx}
                -- Unminimize if needed
                if miniaturized of w then
                    set miniaturized of w to false
                end if
                set t to tab {tab_idx} of w
                select t
                -- Bring window to front
                set index of w to 1
                activate
            end tell
            """
            subprocess.run(
                ["osascript", "-e", select_script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return True

    return False


def _get_cwd_for_tty(tty: str) -> str | None:
    """Get the cwd of the foreground process on a tty."""
    try:
        tty_short = Path(tty).name  # e.g. "ttys000"
        # Get the foreground process PID (stat column contains '+')
        ps_result = subprocess.run(
            ["ps", "-t", tty_short, "-o", "pid=,stat="],
            capture_output=True,
            text=True,
            timeout=3,
        )
        pid = None
        for ps_line in ps_result.stdout.strip().splitlines():
            parts = ps_line.split()
            if len(parts) >= 2 and "+" in parts[1]:
                pid = parts[0]
                break

        if not pid:
            return None

        # Get the cwd of that process
        lsof_result = subprocess.run(
            ["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        for lsof_line in lsof_result.stdout.strip().splitlines():
            if lsof_line.startswith("n"):
                return lsof_line[1:]

        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _cwds_match(resolved: str, target: str) -> bool:
    """Check if resolved cwd matches or is a parent of the target."""
    resolved = resolved.rstrip("/")
    target = target.rstrip("/")
    return resolved == target or target.startswith(resolved + "/")


def _build_script(terminal: str, cwd: str) -> str | None:
    basename = Path(cwd).name

    if terminal == "Ghostty":
        return f"""
        tell application "System Events"
            tell process "Ghostty"
                set allWindows to every window
                repeat with w in allWindows
                    if name of w contains "{basename}" then
                        perform action "AXRaise" of w
                    end if
                end repeat
            end tell
        end tell
        tell application "Ghostty"
            repeat with w in windows
                if miniaturized of w then
                    set miniaturized of w to false
                end if
            end repeat
            activate
        end tell
        return "true"
        """

    if terminal == "Terminal":
        return f"""
        tell application "Terminal"
            repeat with w in windows
                if miniaturized of w then
                    set miniaturized of w to false
                end if
                repeat with t in tabs of w
                    try
                        if custom title of t contains "{basename}" then
                            set selected tab of w to t
                            set index of w to 1
                        end if
                    end try
                end repeat
            end repeat
            activate
        end tell
        return "true"
        """

    if terminal == "Warp":
        # Warp has no AppleScript API for tab switching.
        # Unminimize and bring to front.
        return """
        tell application "System Events"
            tell process "Warp"
                set allWindows to every window
                repeat with w in allWindows
                    try
                        perform action "AXRaise" of w
                    end try
                end repeat
            end tell
        end tell
        tell application "Warp" to activate
        return "true"
        """

    if terminal == "IntelliJ":
        # Find whichever JetBrains IDE is running and bring it to front.
        ide_list = ", ".join(f'"{name}"' for name in JETBRAINS_IDES)
        return f"""
        tell application "System Events"
            set jetbrainsApps to {{{ide_list}}}
            repeat with appName in jetbrainsApps
                if (name of processes) contains (appName as text) then
                    set appFile to application file of (first process whose name is (appName as text))
                    set realName to name of appFile
                    -- Force to front
                    tell process (appName as text)
                        set frontmost to true
                    end tell
                    do shell script "open -a " & quoted form of realName
                    return "true"
                end if
            end repeat
        end tell
        return "false"
        """

    return None
