"""Paths, defaults, and environment variable configuration."""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def utcnow() -> datetime:
    """Return current UTC time as a naive datetime (no deprecation warning)."""
    return datetime.now(UTC).replace(tzinfo=None)


STATE_DIR = Path(os.environ.get("FLAUDE_STATE_DIR", "/tmp/flaude"))
SESSIONS_DIR = STATE_DIR / "state"
LOGS_DIR = STATE_DIR / "logs"
ACTIVITY_LOG = LOGS_DIR / "activity.log"
DASHBOARD_PID = STATE_DIR / "dashboard.pid"

RULES_PATH = Path(
    os.environ.get(
        "FLAUDE_RULES_PATH",
        "~/.config/flaude/rules.yaml",
    )
).expanduser()

CLAUDE_SETTINGS_PATH = Path("~/.claude/settings.json").expanduser()
CONFIG_PATH = Path(
    os.environ.get(
        "FLAUDE_CONFIG_PATH",
        "~/.config/flaude/config.yaml",
    )
).expanduser()

DEFAULT_THEME = "tokyo-night"

STALE_SESSION_TIMEOUT = int(os.environ.get("FLAUDE_STALE_SESSION_TIMEOUT", "28800"))
SOFT_HIDE_TIMEOUT: int | None = (
    int(v) if (v := os.environ.get("FLAUDE_SOFT_HIDE_TIMEOUT")) is not None else None
)
TUI_REFRESH_INTERVAL = float(os.environ.get("FLAUDE_TUI_REFRESH_INTERVAL", "1.0"))
TERMINAL_OVERRIDE = os.environ.get("FLAUDE_TERMINAL")

# All hooks are non-blocking (monitor only), so a short timeout is fine
HOOK_TIMEOUT_DEFAULT = 3

# Identifier used to detect flaude hooks in settings.json.
# Try native Rust binary first, fall back to Python dispatcher.
_HOOK_BINARY = Path(__file__).parent / "bin" / "flaude-hook"
if _HOOK_BINARY.exists() and os.access(_HOOK_BINARY, os.X_OK):
    HOOK_COMMAND = str(_HOOK_BINARY)
else:
    HOOK_COMMAND = f"{sys.executable} -m flaude.hooks.dispatcher"

# Used to identify any flaude hook (Rust or Python) in settings.json
HOOK_COMMAND_PYTHON = f"{sys.executable} -m flaude.hooks.dispatcher"

# Model token limits — single source of truth
MODEL_LIMITS: dict[str, int] = {
    "claude-opus-4-6": 1_000_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5": 200_000,
}
DEFAULT_MODEL_LIMIT = 200_000


def get_model_limit(model: str | None) -> int:
    """Get token limit for a model, with fuzzy fallback for partial names.

    Handles exact IDs ("claude-opus-4-6") and versioned variants
    ("claude-opus-4-20250514") by checking if either string contains
    the model family name (opus/sonnet/haiku).
    """
    if not model:
        return DEFAULT_MODEL_LIMIT
    if model in MODEL_LIMITS:
        return MODEL_LIMITS[model]
    # Fuzzy: check if the model family name appears in the input
    for key, val in MODEL_LIMITS.items():
        # Extract family name (e.g., "opus" from "claude-opus-4-6")
        parts = key.split("-")
        if len(parts) >= 2 and parts[1] in model:
            return val
    return DEFAULT_MODEL_LIMIT


def atomic_write(path: Path, data: str) -> None:
    """Write data to path atomically via a .tmp rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    os.rename(tmp, path)


def ensure_dirs() -> None:
    """Create all required directories if they don't exist."""
    for d in (SESSIONS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)
