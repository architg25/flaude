"""Tests for stale session cleanup logic."""

from datetime import timedelta

import pytest

from helpers import make_state
from flaude.state.cleanup import cleanup_stale_sessions
from flaude.state.models import SessionStatus


def _stale_state(session_id, mgr, age_seconds, **overrides):
    """Create and save a session that last reported `age_seconds` ago."""
    from flaude.constants import utcnow

    past = utcnow() - timedelta(seconds=age_seconds)
    state = make_state(session_id, last_event_at=past, started_at=past, **overrides)
    mgr.save_session(state)
    return state


class TestCleanupStaleSessions:
    def test_hard_timeout_deletes(self, mgr, monkeypatch):
        """Session inactive longer than STALE_SESSION_TIMEOUT is deleted."""
        monkeypatch.setattr("flaude.state.cleanup.STALE_SESSION_TIMEOUT", 1800)
        _stale_state("old", mgr, age_seconds=2000)

        cleaned = cleanup_stale_sessions(mgr)
        assert cleaned == 1
        assert mgr.load_session("old") is None

    def test_soft_check_no_process_deletes(self, mgr, monkeypatch):
        """Session >30s inactive with no process is cleaned up."""
        monkeypatch.setattr("flaude.state.cleanup.STALE_SESSION_TIMEOUT", 1800)
        monkeypatch.setattr("flaude.state.cleanup._get_active_cwds", lambda: set())
        _stale_state("orphan", mgr, age_seconds=60, cwd="/tmp/dead")

        cleaned = cleanup_stale_sessions(mgr)
        assert cleaned == 1
        assert mgr.load_session("orphan") is None

    def test_soft_check_with_process_survives(self, mgr, monkeypatch):
        """Session >30s inactive but with a live process is kept."""
        monkeypatch.setattr("flaude.state.cleanup.STALE_SESSION_TIMEOUT", 1800)
        monkeypatch.setattr(
            "flaude.state.cleanup._get_active_cwds", lambda: {"/tmp/alive"}
        )
        _stale_state("alive", mgr, age_seconds=60, cwd="/tmp/alive")

        cleaned = cleanup_stale_sessions(mgr)
        assert cleaned == 0
        assert mgr.load_session("alive") is not None

    def test_fresh_session_not_touched(self, mgr, monkeypatch):
        """Session < 30s old is not checked at all."""
        monkeypatch.setattr("flaude.state.cleanup.STALE_SESSION_TIMEOUT", 1800)
        _stale_state("fresh", mgr, age_seconds=5)

        cleaned = cleanup_stale_sessions(mgr)
        assert cleaned == 0
        assert mgr.load_session("fresh") is not None

    def test_ended_sessions_deleted(self, mgr, monkeypatch):
        """Sessions with ENDED status are cleaned up regardless of age."""
        monkeypatch.setattr("flaude.state.cleanup.STALE_SESSION_TIMEOUT", 1800)
        _stale_state("ended", mgr, age_seconds=5000, status=SessionStatus.ENDED)

        cleaned = cleanup_stale_sessions(mgr)
        assert cleaned == 1
        assert mgr.load_session("ended") is None

    def test_empty_returns_zero(self, mgr):
        assert cleanup_stale_sessions(mgr) == 0

    def test_returns_correct_count(self, mgr, monkeypatch):
        monkeypatch.setattr("flaude.state.cleanup.STALE_SESSION_TIMEOUT", 1800)
        _stale_state("old1", mgr, age_seconds=2000)
        _stale_state("old2", mgr, age_seconds=3000)
        _stale_state("ok", mgr, age_seconds=5)

        cleaned = cleanup_stale_sessions(mgr)
        assert cleaned == 2
