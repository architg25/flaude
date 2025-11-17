"""Tests for StateManager — save, load, delete, permissions, decisions."""

from datetime import datetime, timedelta

import pytest

from flaude.state.manager import StateManager
from flaude.state.models import SessionState, SessionStatus


def _make_state(session_id: str = "sess-1", **overrides) -> SessionState:
    now = datetime.now()
    defaults = dict(
        session_id=session_id,
        started_at=now,
        last_event_at=now,
    )
    defaults.update(overrides)
    return SessionState(**defaults)


@pytest.fixture()
def mgr(tmp_path):
    sessions_dir = tmp_path / "state"
    decisions_dir = tmp_path / "decisions"
    sessions_dir.mkdir()
    decisions_dir.mkdir()
    return StateManager(sessions_dir=sessions_dir, decisions_dir=decisions_dir)


# -- save / load roundtrip --


def test_save_and_load_roundtrip(mgr):
    state = _make_state(cwd="/home/user", error_count=3)
    mgr.save_session(state)

    loaded = mgr.load_session("sess-1")
    assert loaded is not None
    assert loaded.session_id == "sess-1"
    assert loaded.cwd == "/home/user"
    assert loaded.error_count == 3
    assert loaded.status == SessionStatus.WORKING


def test_load_missing_returns_none(mgr):
    assert mgr.load_session("nonexistent") is None


# -- load_all_sessions --


def test_load_all_sessions(mgr):
    mgr.save_session(_make_state("a"))
    mgr.save_session(_make_state("b"))
    mgr.save_session(_make_state("c"))

    all_sessions = mgr.load_all_sessions()
    assert set(all_sessions.keys()) == {"a", "b", "c"}


def test_load_all_sessions_skips_corrupt(mgr):
    mgr.save_session(_make_state("good"))
    # Write garbage to a .json file
    (mgr.sessions_dir / "bad.json").write_text("{not valid", encoding="utf-8")

    all_sessions = mgr.load_all_sessions()
    assert list(all_sessions.keys()) == ["good"]


def test_load_all_sessions_empty_dir(mgr):
    assert mgr.load_all_sessions() == {}


# -- delete --


def test_delete_session(mgr):
    mgr.save_session(_make_state("doomed"))
    assert mgr.load_session("doomed") is not None

    mgr.delete_session("doomed")
    assert mgr.load_session("doomed") is None


def test_delete_nonexistent_is_noop(mgr):
    mgr.delete_session("ghost")  # should not raise


# -- pending permissions --


def test_add_and_resolve_permission(mgr):
    mgr.save_session(_make_state("sess-p"))
    timeout = datetime.now() + timedelta(seconds=120)

    mgr.add_pending_permission(
        session_id="sess-p",
        request_id="req-1",
        tool_name="Bash",
        tool_input={"command": "rm -rf /"},
        rule_matched="deny_destructive",
        timeout_at=timeout,
    )

    state = mgr.load_session("sess-p")
    assert len(state.pending_permissions) == 1
    assert state.pending_permissions[0].request_id == "req-1"
    assert state.pending_permissions[0].tool_name == "Bash"
    assert state.pending_permissions[0].rule_matched == "deny_destructive"

    mgr.resolve_permission("sess-p", "req-1")

    state = mgr.load_session("sess-p")
    assert len(state.pending_permissions) == 0


def test_add_permission_to_missing_session_is_noop(mgr):
    # Should not raise
    mgr.add_pending_permission(
        session_id="nope",
        request_id="req-x",
        tool_name="Read",
        tool_input={},
        rule_matched=None,
        timeout_at=datetime.now(),
    )


def test_resolve_nonexistent_permission_is_noop(mgr):
    mgr.save_session(_make_state("sess-r"))
    mgr.resolve_permission("sess-r", "no-such-req")  # should not raise


# -- decisions --


def test_write_and_read_decision(mgr):
    decision = {"action": "allow", "reason": "user approved"}
    mgr.write_decision("sess-d", "req-1", decision)

    result = mgr.read_decision("sess-d", "req-1")
    assert result == decision

    # read_decision deletes the file — second read returns None
    assert mgr.read_decision("sess-d", "req-1") is None


def test_read_missing_decision_returns_none(mgr):
    assert mgr.read_decision("sess-x", "req-x") is None


# -- atomic writes --


def test_atomic_write_no_leftover_tmp(mgr):
    """After save, there should be no .tmp files lying around."""
    mgr.save_session(_make_state("atomic"))
    tmp_files = list(mgr.sessions_dir.glob("*.tmp"))
    assert tmp_files == []


def test_atomic_write_produces_valid_json(mgr):
    """The file on disk must be parseable — no partial writes."""
    import json

    state = _make_state("valid", tool_stats={"Bash": 5, "Read": 12})
    mgr.save_session(state)

    raw = (mgr.sessions_dir / "valid.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["session_id"] == "valid"
    assert parsed["tool_stats"] == {"Bash": 5, "Read": 12}
