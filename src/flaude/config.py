"""Shared config loading, saving, and migration for ~/.config/flaude/config.yaml."""

import os

import yaml

from flaude.constants import CONFIG_PATH


def load_config() -> dict:
    """Load config.yaml, returning empty dict on any failure."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    return {}


def save_config(config: dict) -> None:
    """Persist config.yaml atomically. Best-effort, never raises."""
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_PATH.with_suffix(".yaml.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False)
        os.rename(tmp, CONFIG_PATH)
    except Exception:
        pass


def migrate_notifications_config(config: dict) -> dict:
    """Migrate flat notification config to two-category format. Idempotent."""
    notif = config.get("notifications", {})

    # Already migrated if nested category dicts exist
    if isinstance(notif.get("long_turn_completion"), dict):
        return config

    config["notifications"] = {
        "enabled": notif.get("enabled", False),
        "long_turn_completion": {
            "enabled": True,
            "terminal_bell": notif.get("terminal_bell", True),
            "macos_alert": notif.get("macos_alert", False),
            "system_sound": notif.get("system_sound", False),
            "long_turn_minutes": notif.get("long_turn_minutes", 5),
        },
        "waiting_on_input": {
            "enabled": False,
            "terminal_bell": True,
            "macos_alert": False,
            "system_sound": False,
            "delay_seconds": 10,
        },
    }
    return config
