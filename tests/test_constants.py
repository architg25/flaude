"""Tests for flaude.constants helpers."""

from pathlib import Path

from flaude.constants import LOGS_DIR, session_activity_path


def test_session_activity_path():
    path = session_activity_path("abc123-def456")
    assert path == LOGS_DIR / "abc123-def456.activity.jsonl"
    assert isinstance(path, Path)
