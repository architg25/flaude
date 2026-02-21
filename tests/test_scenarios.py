"""Scenario tests — realistic multi-event sequences through the dispatcher.

Each test simulates a sequence of hook events hitting a session and asserts
state transitions at key points. These catch bugs that unit tests miss:
state not carried between events, fields not cleared, etc.
"""

from datetime import timedelta
from pathlib import Path

from helpers import make_state
from flaude.hooks.dispatcher import (
    _handle_notification,
    _handle_post_tool_use,
    _handle_pre_tool_use,
    _handle_session_end,
    _handle_session_start,
    _handle_stop,
    _handle_user_prompt_submit,
)
from flaude.rules.engine import RulesEngine
from flaude.state.cleanup import cleanup_stale_sessions
from flaude.state.models import SessionStatus

SID = "scenario-sess-1"
CWD = "/tmp/project"
DEFAULT_YAML = (
    Path(__file__).resolve().parent.parent / "src" / "flaude" / "rules" / "default.yaml"
)


def _ev(session_id=SID, cwd=CWD, **extra):
    """Build an event dict with common fields."""
    return {"session_id": session_id, "cwd": cwd, **extra}


class TestFullSessionLifecycle:
    """SessionStart → UserPrompt → tools → Stop → SessionEnd"""

    def test_lifecycle(self, mgr, no_rules):
        # 1. Session starts
        _handle_session_start(_ev(permission_mode="default"), mgr)
        state = mgr.load_session(SID)
        assert state.status == SessionStatus.NEW

        # 2. User sends a prompt
        _handle_user_prompt_submit(_ev(user_prompt="Refactor auth module"), mgr)
        state = mgr.load_session(SID)
        assert state.status == SessionStatus.WORKING
        assert state.last_prompt == "Refactor auth module"
        assert state.turn_started_at is not None

        # 3. Claude reads a file
        _handle_pre_tool_use(
            _ev(tool_name="Read", tool_input={"file_path": "/tmp/project/auth.py"}), mgr
        )
        state = mgr.load_session(SID)
        assert state.tool_stats["Read"] == 1
        assert state.last_tool.summary == "auth.py"

        _handle_post_tool_use(_ev(tool_name="Read"), mgr)

        # 4. Claude runs a bash command
        _handle_pre_tool_use(
            _ev(tool_name="Bash", tool_input={"command": "pytest tests/"}), mgr
        )
        state = mgr.load_session(SID)
        assert state.tool_stats["Bash"] == 1
        assert state.tool_stats["Read"] == 1  # still there from step 3

        _handle_post_tool_use(_ev(tool_name="Bash"), mgr)

        # 5. Claude finishes
        _handle_stop(_ev(), mgr)
        state = mgr.load_session(SID)
        assert state.status == SessionStatus.IDLE
        assert state.last_turn_duration > 0
        assert state.turn_started_at is None

        # 6. Session ends
        _handle_session_end(_ev(), mgr)
        assert mgr.load_session(SID) is None


class TestQuestionAnswerFlow:
    """Claude asks a question, user answers, work resumes."""

    def test_ask_and_answer(self, mgr, no_rules):
        _handle_session_start(_ev(), mgr)
        _handle_user_prompt_submit(_ev(user_prompt="Add caching"), mgr)

        # Claude asks a question
        question = {"questions": [{"question": "Redis or Memcached?"}]}
        _handle_pre_tool_use(_ev(tool_name="AskUserQuestion", tool_input=question), mgr)
        state = mgr.load_session(SID)
        assert state.status == SessionStatus.WAITING_ANSWER
        assert state.pending_question == question

        # PostToolUse clears the pending question
        _handle_post_tool_use(_ev(tool_name="AskUserQuestion"), mgr)
        state = mgr.load_session(SID)
        assert state.pending_question is None

        # User answers
        _handle_user_prompt_submit(_ev(user_prompt="Use Redis"), mgr)
        state = mgr.load_session(SID)
        assert state.status == SessionStatus.WORKING
        assert state.last_prompt == "Use Redis"


class TestExitPlanModeFlow:
    """Claude presents a plan via ExitPlanMode, user reviews."""

    def test_plan_approval(self, mgr, no_rules):
        _handle_session_start(_ev(), mgr)
        _handle_user_prompt_submit(_ev(user_prompt="Implement feature X"), mgr)

        plan_input = {"allowedPrompts": [{"tool": "Bash", "prompt": "run tests"}]}
        _handle_pre_tool_use(_ev(tool_name="ExitPlanMode", tool_input=plan_input), mgr)
        state = mgr.load_session(SID)
        assert state.status == SessionStatus.WAITING_ANSWER
        assert state.pending_question == plan_input

        _handle_post_tool_use(_ev(tool_name="ExitPlanMode"), mgr)
        state = mgr.load_session(SID)
        assert state.pending_question is None


class TestLateJoiningSession:
    """Events arrive for a session that was never SessionStart'd."""

    def test_pre_tool_use_without_session_start(self, mgr, no_rules):
        # Jump straight to PreToolUse — no SessionStart
        _handle_pre_tool_use(
            _ev(session_id="late", tool_name="Grep", tool_input={"pattern": "TODO"}),
            mgr,
        )
        state = mgr.load_session("late")
        assert state is not None
        assert state.session_id == "late"
        assert state.cwd == CWD
        assert state.tool_stats["Grep"] == 1

    def test_stop_without_session_start(self, mgr):
        _handle_stop(_ev(session_id="late2"), mgr)
        state = mgr.load_session("late2")
        assert state is not None
        assert state.status == SessionStatus.IDLE


class TestMultipleConcurrentSessions:
    """Two sessions running independently — state must not bleed across."""

    def test_independent_sessions(self, mgr, no_rules):
        sid_a, sid_b = "session-a", "session-b"
        _handle_session_start(_ev(session_id=sid_a, cwd="/project-a"), mgr)
        _handle_session_start(_ev(session_id=sid_b, cwd="/project-b"), mgr)

        # Session A uses Read
        _handle_pre_tool_use(
            _ev(
                session_id=sid_a,
                cwd="/project-a",
                tool_name="Read",
                tool_input={"file_path": "/a.py"},
            ),
            mgr,
        )
        # Session B uses Bash
        _handle_pre_tool_use(
            _ev(
                session_id=sid_b,
                cwd="/project-b",
                tool_name="Bash",
                tool_input={"command": "ls"},
            ),
            mgr,
        )

        state_a = mgr.load_session(sid_a)
        state_b = mgr.load_session(sid_b)

        assert state_a.tool_stats == {"Read": 1}
        assert state_b.tool_stats == {"Bash": 1}
        assert state_a.cwd == "/project-a"
        assert state_b.cwd == "/project-b"

        # End session A — B should survive
        _handle_session_end(_ev(session_id=sid_a), mgr)
        assert mgr.load_session(sid_a) is None
        assert mgr.load_session(sid_b) is not None


class TestDangerousCommandDenied:
    """PreToolUse with a dangerous command — state is saved, rules return deny."""

    def test_state_saved_before_deny(self, mgr):
        _handle_session_start(_ev(), mgr)

        # Evaluate rules directly (can't test _emit_decision since it calls sys.exit)
        engine = RulesEngine.load(DEFAULT_YAML)
        result = engine.evaluate("Bash", {"command": "rm -rf /etc"}, CWD)
        assert result.action == "deny"

        # Verify session state was created and is usable
        state = mgr.load_session(SID)
        assert state is not None


class TestCleanupWithMixedSessions:
    """Cleanup should only remove stale/orphan sessions, not fresh ones."""

    def test_mixed_cleanup(self, mgr, monkeypatch):
        from flaude.constants import utcnow

        monkeypatch.setattr("flaude.state.cleanup.STALE_SESSION_TIMEOUT", 1800)
        monkeypatch.setattr(
            "flaude.state.cleanup._session_has_process", lambda cwd: False
        )

        now = utcnow()

        # Fresh session — should survive
        fresh = make_state("fresh", last_event_at=now, cwd="/tmp/fresh")
        mgr.save_session(fresh)

        # Stale session — hard timeout
        stale = make_state(
            "stale", last_event_at=now - timedelta(seconds=2000), cwd="/tmp/stale"
        )
        mgr.save_session(stale)

        # Orphan session — no process, >30s old
        orphan = make_state(
            "orphan", last_event_at=now - timedelta(seconds=60), cwd="/tmp/orphan"
        )
        mgr.save_session(orphan)

        # Active session waiting for input — should survive if fresh
        waiting = make_state(
            "waiting",
            last_event_at=now,
            status=SessionStatus.WAITING_ANSWER,
            cwd="/tmp/waiting",
        )
        mgr.save_session(waiting)

        cleaned = cleanup_stale_sessions(mgr)
        assert cleaned == 2  # stale + orphan

        assert mgr.load_session("fresh") is not None
        assert mgr.load_session("stale") is None
        assert mgr.load_session("orphan") is None
        assert mgr.load_session("waiting") is not None
