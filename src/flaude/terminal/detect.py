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

# JetBrains IDE process names
JETBRAINS_IDES = [
    "IntelliJ IDEA",
    "PyCharm",
    "WebStorm",
    "GoLand",
    "PhpStorm",
    "Android Studio",
]


def detect_terminal() -> str | None:
    """Detect which terminal emulator is running.

    Returns the terminal name (e.g., "iTerm2") or None if unknown.
    """
    if TERMINAL_OVERRIDE:
        return TERMINAL_OVERRIDE

    for name, process_name in KNOWN_TERMINALS:
        try:
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'tell application "System Events" to (name of processes) contains "{process_name}"',
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if "true" in result.stdout.lower():
                return name
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    # Check for JetBrains IDEs
    for ide_name in JETBRAINS_IDES:
        try:
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'tell application "System Events" to (name of processes) contains "{ide_name}"',
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if "true" in result.stdout.lower():
                return "IntelliJ"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    return None
