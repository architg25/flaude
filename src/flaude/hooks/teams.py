"""Team config accessors shared by dispatcher and scanner."""

from __future__ import annotations

import json
from pathlib import Path


def read_lead_session_id(team_name: str) -> str | None:
    """Read leadSessionId from the team config file."""
    try:
        config_path = Path(f"~/.claude/teams/{team_name}/config.json").expanduser()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        return config.get("leadSessionId")
    except (OSError, json.JSONDecodeError, KeyError):
        return None
