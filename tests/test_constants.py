"""Tests for constants module — utility functions."""

from datetime import datetime, timezone
from pathlib import Path

from flaude.constants import (
    DEFAULT_MODEL_LIMIT,
    atomic_write,
    ensure_dirs,
    get_model_limit,
    utcnow,
)


# -- utcnow --


def test_utcnow_returns_naive_datetime():
    now = utcnow()
    assert now.tzinfo is None


def test_utcnow_returns_recent_time():
    from datetime import datetime, timedelta

    now = utcnow()
    # Should be within a few seconds of real UTC
    diff = abs(datetime.now(timezone.utc).replace(tzinfo=None) - now)
    assert diff < timedelta(seconds=2)


# -- get_model_limit --


def test_get_model_limit_exact_match():
    assert get_model_limit("claude-opus-4-6") == 1_000_000
    assert get_model_limit("claude-sonnet-4-6") == 200_000
    assert get_model_limit("claude-haiku-4-5") == 200_000


def test_get_model_limit_fuzzy_match():
    assert get_model_limit("claude-opus-4-20250514") == 1_000_000
    assert get_model_limit("claude-sonnet-4-20250514") == 200_000


def test_get_model_limit_unknown_model():
    assert get_model_limit("gpt-4o") == DEFAULT_MODEL_LIMIT


def test_get_model_limit_none():
    assert get_model_limit(None) == DEFAULT_MODEL_LIMIT


def test_get_model_limit_empty_string():
    assert get_model_limit("") == DEFAULT_MODEL_LIMIT


# -- atomic_write --


def test_atomic_write_creates_file(tmp_path):
    target = tmp_path / "out.txt"
    atomic_write(target, "hello")

    assert target.read_text(encoding="utf-8") == "hello"


def test_atomic_write_overwrites_existing(tmp_path):
    target = tmp_path / "out.txt"
    target.write_text("old", encoding="utf-8")

    atomic_write(target, "new")

    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_write_no_leftover_tmp(tmp_path):
    target = tmp_path / "out.txt"
    atomic_write(target, "data")

    tmp_file = target.with_suffix(".txt.tmp")
    assert not tmp_file.exists()


def test_atomic_write_creates_parent_dirs(tmp_path):
    target = tmp_path / "a" / "b" / "file.json"
    atomic_write(target, '{"ok": true}')

    assert target.exists()
    assert target.read_text(encoding="utf-8") == '{"ok": true}'


# -- ensure_dirs --


def test_ensure_dirs_creates_directories(tmp_path, monkeypatch):
    import flaude.constants as const

    sessions = tmp_path / "state"
    logs = tmp_path / "logs"
    monkeypatch.setattr(const, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(const, "LOGS_DIR", logs)

    ensure_dirs()

    assert sessions.is_dir()
    assert logs.is_dir()


def test_ensure_dirs_idempotent(tmp_path, monkeypatch):
    import flaude.constants as const

    sessions = tmp_path / "state"
    logs = tmp_path / "logs"
    monkeypatch.setattr(const, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(const, "LOGS_DIR", logs)

    ensure_dirs()
    ensure_dirs()  # should not raise

    assert sessions.is_dir()
    assert logs.is_dir()
