"""Detect the active terminal application on macOS."""

import os
import subprocess

from flaude.constants import TERMINAL_OVERRIDE

_TERM_PROGRAM_MAP = {
    "iTerm.app": "iTerm2",
    "ghostty": "Ghostty",
    "Apple_Terminal": "Terminal",
    "WarpTerminal": "Warp",
}

# Terminal apps in preference order (fallback: scan running processes)
KNOWN_TERMINALS = [
    ("iTerm2", "iTerm2"),
    ("Ghostty", "Ghostty"),
    ("Terminal", "Terminal"),
    ("Warp", "Warp"),
]

# JetBrains IDE process names (both display names and actual process names)
JETBRAINS_IDES = [
    "idea",
    "IntelliJ IDEA",
    "pycharm",
    "PyCharm",
    "webstorm",
    "WebStorm",
    "goland",
    "GoLand",
    "phpstorm",
    "PhpStorm",
    "studio",
    "Android Studio",
]


def detect_terminal() -> str | None:
    """Detect which terminal flaude is running in.

    Checks TERM_PROGRAM first (accurate — set by the actual terminal),
    then falls back to scanning running processes (ambiguous when
    multiple terminals are open).
    """
    if TERMINAL_OVERRIDE:
        return TERMINAL_OVERRIDE

    # Precise: TERM_PROGRAM is set by the terminal we're actually inside
    term = os.environ.get("TERM_PROGRAM", "")
    if term in _TERM_PROGRAM_MAP:
        return _TERM_PROGRAM_MAP[term]
    if "JetBrains" in os.environ.get("TERMINAL_EMULATOR", ""):
        return "IntelliJ"

    # Fallback: scan running processes (picks first match, may be wrong)
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of every process',
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        processes = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    for name, process_name in KNOWN_TERMINALS:
        if process_name in processes:
            return name

    for ide_name in JETBRAINS_IDES:
        if ide_name in processes:
            return "IntelliJ"

    return None
