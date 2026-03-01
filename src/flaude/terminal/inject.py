"""Send text to a Claude Code session's terminal via AppleScript."""

import subprocess

from flaude.terminal.navigate import escape_applescript


def send_text_to_session(tty: str, text: str) -> bool:
    """Send text to an iTerm2 session identified by tty device.

    Uses iTerm2's AppleScript API to find the session matching the given tty
    and write the text followed by a carriage return (Enter key).

    Returns True if the text was sent, False on failure.
    """
    if not tty or not text:
        return False

    tty_escaped = escape_applescript(tty)

    escaped = escape_applescript(text)
    # Embed newlines as AppleScript linefeed concatenation.
    # Claude Code treats \n as Shift+Enter (new line) and \r as Enter (submit).
    as_text = '"' + escaped.replace("\n", '" & linefeed & "') + '"'

    script = f"""
    tell application "iTerm2"
        repeat with w in windows
            repeat with t in tabs of w
                repeat with s in sessions of t
                    if tty of s is "{tty_escaped}" then
                        tell s
                            write text {as_text} without newline
                            write text (character id 13) without newline
                        end tell
                        return "sent"
                    end if
                end repeat
            end repeat
        end repeat
        return "not_found"
    end tell
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "sent" in result.stdout.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
