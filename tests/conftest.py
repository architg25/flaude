"""Shared fixtures for flaude tests."""

import pytest

from flaude.state.manager import StateManager


@pytest.fixture()
def mgr(tmp_path):
    sessions_dir = tmp_path / "state"
    sessions_dir.mkdir()
    return StateManager(sessions_dir=sessions_dir)
