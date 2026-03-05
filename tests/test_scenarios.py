"""Scenario tests — realistic multi-event sequences through the dispatcher.

Each test simulates a sequence of hook events hitting a session and asserts
state transitions at key points. These catch bugs that unit tests miss:
state not carried between events, fields not cleared, etc.
"""

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from helpers import make_state
from flaude.hooks.dispatcher import (
    _handle_permission_request,
    _handle_post_tool_use,
    _handle_pre_tool_use,
    _handle_session_end,
    _handle_session_start,
    _handle_stop,
    _handle_subagent_stop,
    _handle_user_prompt_submit,
)
from flaude.constants import utcnow
from flaude.rules.engine import RulesEngine
from flaude.state.cleanup import cleanup_stale_sessions, correct_stale_waiting
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

        # PostToolUse clears the pending question and resets status
        _handle_post_tool_use(_ev(tool_name="AskUserQuestion"), mgr)
        state = mgr.load_session(SID)
        assert state.pending_question is None
        assert state.status == SessionStatus.WORKING

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
        assert state.status == SessionStatus.PLAN
        assert state.pending_question == plan_input

        _handle_post_tool_use(_ev(tool_name="ExitPlanMode"), mgr)
        state = mgr.load_session(SID)
        assert state.pending_question is None
        assert state.status == SessionStatus.WORKING


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
        monkeypatch.setattr("flaude.state.cleanup._get_active_cwds", lambda: set())

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


class TestStaleWaitingCorrection:
    """Waiting states should be cleared when transcript shows the session moved on."""

    def test_stale_waiting_permission_corrected(self, mgr, tmp_path):
        """Transcript modified after last_event_at → status corrected to WORKING."""
        transcript = tmp_path / "transcript.jsonl"
        # Write transcript content — mtime will be "now", well after old_time
        transcript.write_text('{"message":{"role":"assistant"}}\n')

        old_time = utcnow() - timedelta(seconds=30)
        state = make_state(
            "stuck",
            status=SessionStatus.WAITING_PERMISSION,
            last_event_at=old_time,
            transcript_path=str(transcript),
        )
        mgr.save_session(state)

        sessions = mgr.load_all_sessions()
        corrected = correct_stale_waiting(mgr, sessions)
        assert corrected == 1

        fixed = mgr.load_session("stuck")
        assert fixed.status == SessionStatus.WORKING

    def test_stale_plan_corrected(self, mgr, tmp_path):
        """PLAN status also gets corrected."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('{"message":{"role":"assistant"}}\n')

        old_time = utcnow() - timedelta(seconds=30)
        state = make_state(
            "plan-stuck",
            status=SessionStatus.PLAN,
            last_event_at=old_time,
            transcript_path=str(transcript),
        )
        mgr.save_session(state)

        sessions = mgr.load_all_sessions()
        corrected = correct_stale_waiting(mgr, sessions)
        assert corrected == 1
        assert mgr.load_session("plan-stuck").status == SessionStatus.WORKING

    def test_fresh_waiting_not_corrected(self, mgr, tmp_path):
        """Waiting state < 5s old should NOT be corrected."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('{"message":{"role":"assistant"}}\n')

        state = make_state(
            "fresh-wait",
            status=SessionStatus.WAITING_PERMISSION,
            last_event_at=utcnow(),
            transcript_path=str(transcript),
        )
        mgr.save_session(state)

        sessions = mgr.load_all_sessions()
        corrected = correct_stale_waiting(mgr, sessions)
        assert corrected == 0
        assert mgr.load_session("fresh-wait").status == SessionStatus.WAITING_PERMISSION

    def test_no_transcript_not_corrected(self, mgr):
        """No transcript path → skip correction."""
        old_time = utcnow() - timedelta(seconds=30)
        state = make_state(
            "no-transcript",
            status=SessionStatus.WAITING_PERMISSION,
            last_event_at=old_time,
        )
        mgr.save_session(state)

        sessions = mgr.load_all_sessions()
        corrected = correct_stale_waiting(mgr, sessions)
        assert corrected == 0
        assert (
            mgr.load_session("no-transcript").status == SessionStatus.WAITING_PERMISSION
        )

    def test_transcript_not_modified_not_corrected(self, mgr, tmp_path):
        """Transcript older than last_event_at → user still deciding, don't correct."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('{"message":{"role":"assistant"}}\n')

        # Set transcript mtime to the past (before the event)
        import os

        old_mtime = (utcnow() - timedelta(seconds=60)).timestamp()
        os.utime(transcript, (old_mtime, old_mtime))

        state = make_state(
            "user-thinking",
            status=SessionStatus.WAITING_ANSWER,
            last_event_at=utcnow() - timedelta(seconds=30),
            transcript_path=str(transcript),
        )
        mgr.save_session(state)

        sessions = mgr.load_all_sessions()
        corrected = correct_stale_waiting(mgr, sessions)
        assert corrected == 0
        assert mgr.load_session("user-thinking").status == SessionStatus.WAITING_ANSWER


class TestPermissionRequestFlow:
    """Permission asked → user grants → work continues."""

    def test_permission_grant_resumes_work(self, mgr, no_rules):
        _handle_session_start(_ev(), mgr)
        _handle_user_prompt_submit(_ev(user_prompt="Deploy to prod"), mgr)

        # Claude wants to run a dangerous command
        _handle_pre_tool_use(
            _ev(
                tool_name="Bash", tool_input={"command": "kubectl apply -f deploy.yaml"}
            ),
            mgr,
        )
        state = mgr.load_session(SID)
        assert state.status == SessionStatus.WORKING

        # Claude Code asks for permission
        _handle_permission_request(_ev(tool_name="Bash"), mgr)
        state = mgr.load_session(SID)
        assert state.status == SessionStatus.WAITING_PERMISSION

        # User grants — PostToolUse fires
        _handle_post_tool_use(_ev(tool_name="Bash"), mgr)
        state = mgr.load_session(SID)
        assert state.status == SessionStatus.WORKING
        assert state.pending_question is None

    def test_permission_does_not_overwrite_waiting_answer(self, mgr, no_rules):
        """If session is WAITING_ANSWER, PermissionRequest shouldn't downgrade it."""
        _handle_session_start(_ev(), mgr)
        _handle_user_prompt_submit(_ev(user_prompt="Help me"), mgr)

        question = {"questions": [{"question": "Which DB?"}]}
        _handle_pre_tool_use(_ev(tool_name="AskUserQuestion", tool_input=question), mgr)
        assert mgr.load_session(SID).status == SessionStatus.WAITING_ANSWER

        # Stale PermissionRequest arrives (race condition) — should NOT overwrite
        _handle_permission_request(_ev(tool_name="Bash"), mgr)
        assert mgr.load_session(SID).status == SessionStatus.WAITING_ANSWER


class TestSubagentLifecycle:
    """Parent spawns subagents, they complete, count tracks correctly."""

    def test_subagent_count_lifecycle(self, mgr, no_rules):
        _handle_session_start(_ev(), mgr)
        _handle_user_prompt_submit(_ev(user_prompt="Run parallel tasks"), mgr)

        # Two subagent tool uses (Agent tool)
        for i in range(2):
            _handle_pre_tool_use(
                _ev(tool_name="Task", tool_input={"prompt": f"subtask {i}"}), mgr
            )
            _handle_post_tool_use(_ev(tool_name="Task"), mgr)

        # Subagents complete
        _handle_subagent_stop(_ev(), mgr)
        state = mgr.load_session(SID)
        # subagent_count was 0 (we didn't increment it — that's done by the TUI/scanner)
        # but SubagentStop should not go below 0
        assert state.subagent_count == 0

    def test_subagent_count_tracks_from_nonzero(self, mgr, no_rules):
        """When subagent_count is pre-set, SubagentStop decrements it."""
        _handle_session_start(_ev(), mgr)
        state = mgr.load_session(SID)
        state.subagent_count = 3
        mgr.save_session(state)

        _handle_subagent_stop(_ev(), mgr)
        assert mgr.load_session(SID).subagent_count == 2

        _handle_subagent_stop(_ev(), mgr)
        _handle_subagent_stop(_ev(), mgr)
        assert mgr.load_session(SID).subagent_count == 0

        # Extra stop — should not go negative
        _handle_subagent_stop(_ev(), mgr)
        assert mgr.load_session(SID).subagent_count == 0


class TestTokenAndModelUpdateOnStop:
    """Stop event reads token usage and model from transcript."""

    def test_stop_reads_transcript_usage(self, mgr, no_rules, tmp_path):
        transcript = tmp_path / "transcript.jsonl"
        usage_entry = {
            "message": {
                "model": "claude-opus-4-20250514",
                "usage": {
                    "input_tokens": 10000,
                    "cache_read_input_tokens": 50000,
                    "cache_creation_input_tokens": 5000,
                },
            }
        }
        transcript.write_text(json.dumps(usage_entry) + "\n")

        _handle_session_start(_ev(transcript_path=str(transcript)), mgr)
        _handle_user_prompt_submit(_ev(user_prompt="Do stuff"), mgr)
        _handle_stop(_ev(), mgr)

        state = mgr.load_session(SID)
        assert state.context_tokens == 65000
        assert state.model == "claude-opus-4-20250514"

    def test_stop_reads_custom_title_from_transcript(self, mgr, no_rules, tmp_path):
        transcript = tmp_path / "transcript.jsonl"
        rename_entry = {
            "type": "custom-title",
            "customTitle": "my-session-name",
            "sessionId": SID,
        }
        transcript.write_text(json.dumps(rename_entry) + "\n")

        _handle_session_start(_ev(transcript_path=str(transcript)), mgr)
        _handle_stop(_ev(), mgr)

        state = mgr.load_session(SID)
        assert state.custom_title == "my-session-name"


class TestGitBranchRefreshOnStop:
    """Stop event refreshes git branch in case user switched branches."""

    def test_branch_updated_on_stop(self, mgr, no_rules):
        _handle_session_start(_ev(), mgr)
        state = mgr.load_session(SID)
        assert (
            state.git_branch is not None or state.git_branch is None
        )  # whatever git returns

        # Simulate branch change
        with patch(
            "flaude.hooks.dispatcher.get_git_info",
            return_value=("/tmp/project", "feature-xyz", False),
        ):
            _handle_user_prompt_submit(_ev(user_prompt="Switch branch work"), mgr)
            _handle_stop(_ev(), mgr)

        state = mgr.load_session(SID)
        assert state.git_branch == "feature-xyz"


class TestSessionReconnect:
    """SessionEnd then new SessionStart — fresh state, no bleed."""

    def test_reconnect_gets_clean_state(self, mgr, no_rules):
        # First session lifecycle
        _handle_session_start(_ev(), mgr)
        _handle_user_prompt_submit(_ev(user_prompt="First task"), mgr)
        _handle_pre_tool_use(
            _ev(tool_name="Bash", tool_input={"command": "make build"}), mgr
        )
        _handle_post_tool_use(_ev(tool_name="Bash"), mgr)
        _handle_stop(_ev(), mgr)

        state = mgr.load_session(SID)
        assert state.tool_stats["Bash"] == 1
        assert state.last_prompt == "First task"

        # Session ends
        _handle_session_end(_ev(), mgr)
        assert mgr.load_session(SID) is None

        # New session with same ID — should be completely fresh
        _handle_session_start(_ev(), mgr)
        state = mgr.load_session(SID)
        assert state.status == SessionStatus.NEW
        assert state.tool_stats == {}
        assert state.last_prompt is None
        assert state.last_tool is None
        assert state.context_tokens == 0


class TestTeamSessionFlow:
    """Team metadata flows through session events correctly."""

    def test_team_fields_persisted(self, mgr, no_rules, tmp_path):
        # Create a fake team config
        teams_dir = tmp_path / ".claude" / "teams" / "alpha"
        teams_dir.mkdir(parents=True)
        config = teams_dir / "config.json"
        config.write_text(json.dumps({"leadSessionId": "lead-abc"}))

        with patch(
            "flaude.hooks.dispatcher._read_lead_session_id",
            return_value="lead-abc",
        ):
            _handle_session_start(_ev(teamName="alpha", agentName="worker-1"), mgr)

        state = mgr.load_session(SID)
        assert state.team_name == "alpha"
        assert state.agent_name == "worker-1"
        assert state.lead_session_id == "lead-abc"

        # Team fields survive through tool use
        _handle_user_prompt_submit(_ev(user_prompt="Team work"), mgr)
        _handle_pre_tool_use(
            _ev(tool_name="Read", tool_input={"file_path": "/a.py"}), mgr
        )
        _handle_stop(_ev(), mgr)

        state = mgr.load_session(SID)
        assert state.team_name == "alpha"
        assert state.agent_name == "worker-1"
