"""Detect the active terminal application on macOS."""

import subprocess

from flaude.constants import TERMINAL_OVERRIDE

# Terminal apps in preference order
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
    """Detect which terminal emulator is running.

    Returns the terminal name (e.g., "iTerm2") or None if unknown.
    """
    if TERMINAL_OVERRIDE:
        return TERMINAL_OVERRIDE

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
