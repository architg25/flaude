"""Paths, defaults, and environment variable configuration."""

import os
from datetime import UTC, datetime
from pathlib import Path


def utcnow() -> datetime:
    """Return current UTC time as a naive datetime (no deprecation warning)."""
    return datetime.now(UTC).replace(tzinfo=None)


STATE_DIR = Path(os.environ.get("FLAUDE_STATE_DIR", "/tmp/flaude"))
SESSIONS_DIR = STATE_DIR / "state"
DECISIONS_DIR = STATE_DIR / "decisions"
LOGS_DIR = STATE_DIR / "logs"
ACTIVITY_LOG = LOGS_DIR / "activity.log"
DASHBOARD_PID = STATE_DIR / "dashboard.pid"

RULES_PATH = Path(
    os.environ.get(
        "FLAUDE_RULES_PATH",
        os.path.expanduser("~/.config/flaude/rules.yaml"),
    )
)

CLAUDE_SETTINGS_PATH = Path(os.path.expanduser("~/.claude/settings.json"))

STALE_SESSION_TIMEOUT = int(os.environ.get("FLAUDE_STALE_SESSION_TIMEOUT", "1800"))
TUI_REFRESH_INTERVAL = float(os.environ.get("FLAUDE_TUI_REFRESH_INTERVAL", "1.0"))
TERMINAL_OVERRIDE = os.environ.get("FLAUDE_TERMINAL")

# All hooks are non-blocking (monitor only), so a short timeout is fine
HOOK_TIMEOUT_DEFAULT = 10

# Identifier used to detect flaude hooks in settings.json
HOOK_COMMAND = "python3 -m flaude.hooks.dispatcher"


def ensure_dirs() -> None:
    """Create all required directories if they don't exist."""
    for d in (SESSIONS_DIR, DECISIONS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)
