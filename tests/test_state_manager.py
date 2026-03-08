"""Tests for StateManager — save, load, delete."""

from flaude.state.models import LoopInfo, SessionStatus

from helpers import make_state


# -- save / load roundtrip --


def test_save_and_load_roundtrip(mgr):
    state = make_state(cwd="/home/user", error_count=3)
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
    mgr.save_session(make_state("a"))
    mgr.save_session(make_state("b"))
    mgr.save_session(make_state("c"))

    all_sessions = mgr.load_all_sessions()
    assert set(all_sessions.keys()) == {"a", "b", "c"}


def test_load_all_sessions_skips_corrupt(mgr):
    mgr.save_session(make_state("good"))
    # Write garbage to a .json file
    (mgr.sessions_dir / "bad.json").write_text("{not valid", encoding="utf-8")

    all_sessions = mgr.load_all_sessions()
    assert list(all_sessions.keys()) == ["good"]


def test_load_all_sessions_empty_dir(mgr):
    assert mgr.load_all_sessions() == {}


# -- delete --


def test_delete_session(mgr):
    mgr.save_session(make_state("doomed"))
    assert mgr.load_session("doomed") is not None

    mgr.delete_session("doomed")
    assert mgr.load_session("doomed") is None


def test_delete_nonexistent_is_noop(mgr):
    mgr.delete_session("ghost")  # should not raise


# -- atomic writes --


def test_atomic_write_no_leftover_tmp(mgr):
    """After save, there should be no .tmp files lying around."""
    mgr.save_session(make_state("atomic"))
    tmp_files = list(mgr.sessions_dir.glob("*.tmp"))
    assert tmp_files == []


def test_atomic_write_produces_valid_json(mgr):
    """The file on disk must be parseable — no partial writes."""
    import json

    state = make_state("valid", tool_stats={"Bash": 5, "Read": 12})
    mgr.save_session(state)

    raw = (mgr.sessions_dir / "valid.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["session_id"] == "valid"
    assert parsed["tool_stats"] == {"Bash": 5, "Read": 12}


class TestLoopsField:
    def test_default_empty(self):
        state = make_state()
        assert state.loops == {}

    def test_roundtrip(self, mgr):
        loop = LoopInfo(
            task_id="abcd1234",
            cron_expr="*/5 * * * *",
            human_schedule="Every 5 minutes",
            prompt="check deploy",
            recurring=True,
            created_at="2026-03-08T12:00:00",
        )
        state = make_state(loops={"abcd1234": loop})
        mgr.save_session(state)
        loaded = mgr.load_session(state.session_id)
        assert loaded.loops["abcd1234"].task_id == "abcd1234"
        assert loaded.loops["abcd1234"].cron_expr == "*/5 * * * *"
        assert loaded.loops["abcd1234"].human_schedule == "Every 5 minutes"
        assert loaded.loops["abcd1234"].prompt == "check deploy"
        assert loaded.loops["abcd1234"].recurring is True

    def test_backward_compat_no_loops_field(self, mgr):
        """Old state files without loops field load fine with empty dict."""
        state = make_state()
        mgr.save_session(state)
        loaded = mgr.load_session(state.session_id)
        assert loaded.loops == {}
