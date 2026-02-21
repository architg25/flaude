"""Shared fixtures for flaude tests."""

import pytest

from flaude.state.manager import StateManager


@pytest.fixture()
def mgr(tmp_path):
    sessions_dir = tmp_path / "state"
    sessions_dir.mkdir()
    return StateManager(sessions_dir=sessions_dir)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Clear terminal env vars so _detect_terminal_from_env returns None
    unless a test explicitly sets them."""
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.delenv("TERMINAL_EMULATOR", raising=False)


@pytest.fixture()
def no_rules(monkeypatch):
    """Patch RulesEngine.load to return an empty engine (no rules fire)."""
    from flaude.rules.engine import RulesEngine

    monkeypatch.setattr(
        RulesEngine, "load", classmethod(lambda cls: RulesEngine(rules=[]))
    )
