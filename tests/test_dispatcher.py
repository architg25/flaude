"""Tests for hooks/dispatcher.py — terminal detection,
transcript parsing, and event handlers."""

import json
from datetime import datetime, timedelta, timezone

from helpers import make_state
from flaude.hooks.dispatcher import (
    _detect_terminal_from_env,
    _get_usage_from_transcript,
    _handle_permission_request,
    _handle_post_tool_use,
    _handle_pre_tool_use,
    _handle_session_end,
    _handle_session_start,
    _handle_stop,
    _handle_subagent_stop,
    _handle_user_prompt_submit,
    _load_or_create,
    _log,
)
from flaude.state.models import LoopInfo, SessionStatus


# ---------------------------------------------------------------------------
# _detect_terminal_from_env
# ---------------------------------------------------------------------------


class TestDetectTerminal:
    def test_iterm(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        assert _detect_terminal_from_env() == "iTerm2"

    def test_ghostty(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "ghostty")
        assert _detect_terminal_from_env() == "Ghostty"

    def test_apple_terminal(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
        assert _detect_terminal_from_env() == "Terminal"

    def test_warp(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "WarpTerminal")
        assert _detect_terminal_from_env() == "Warp"

    def test_jetbrains(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "something-else")
        monkeypatch.setenv("TERMINAL_EMULATOR", "JetBrains-JediTerm")
        assert _detect_terminal_from_env() == "IntelliJ"

    def test_unknown_returns_none(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "unknown-term")
        assert _detect_terminal_from_env() is None

    def test_empty_env_returns_none(self):
        # clean_env autouse fixture already cleared these
        assert _detect_terminal_from_env() is None


# ---------------------------------------------------------------------------
# _get_usage_from_transcript
# ---------------------------------------------------------------------------


class TestGetUsageFromTranscript:
    def test_none_path(self):
        assert _get_usage_from_transcript(None) == (0, None, None)

    def test_missing_file(self, tmp_path):
        assert _get_usage_from_transcript(str(tmp_path / "nope.jsonl")) == (
            0,
            None,
            None,
        )

    def test_valid_usage(self, tmp_path):
        transcript = tmp_path / "transcript.jsonl"
        entry = {
            "message": {
                "model": "claude-sonnet-4-20250514",
                "usage": {
                    "input_tokens": 1000,
                    "cache_read_input_tokens": 5000,
                    "cache_creation_input_tokens": 200,
                },
            }
        }
        transcript.write_text(json.dumps(entry) + "\n")
        tokens, model, custom_title = _get_usage_from_transcript(str(transcript))
        assert tokens == 6200
        assert model == "claude-sonnet-4-20250514"
        assert custom_title is None

    def test_no_usage_entries(self, tmp_path):
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(json.dumps({"type": "text"}) + "\n")
        assert _get_usage_from_transcript(str(transcript)) == (0, None, None)

    def test_corrupt_lines_skipped(self, tmp_path):
        transcript = tmp_path / "transcript.jsonl"
        good = {
            "message": {
                "model": "opus",
                "usage": {
                    "input_tokens": 500,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            }
        }
        lines = ["not json at all", json.dumps(good)]
        transcript.write_text("\n".join(lines) + "\n")
        tokens, model, custom_title = _get_usage_from_transcript(str(transcript))
        assert tokens == 500
        assert model == "opus"
        assert custom_title is None

    def test_takes_latest_usage(self, tmp_path):
        """When multiple usage entries exist, the last one wins."""
        transcript = tmp_path / "transcript.jsonl"
        old = {
            "message": {
                "model": "old-model",
                "usage": {
                    "input_tokens": 100,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            }
        }
        new = {
            "message": {
                "model": "new-model",
                "usage": {
                    "input_tokens": 999,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            }
        }
        transcript.write_text(json.dumps(old) + "\n" + json.dumps(new) + "\n")
        tokens, model, custom_title = _get_usage_from_transcript(str(transcript))
        assert tokens == 999
        assert model == "new-model"
        assert custom_title is None

    def test_reads_custom_title_from_rename_entry(self, tmp_path):
        """/rename writes a custom-title entry."""
        transcript = tmp_path / "transcript.jsonl"
        rename_entry = {
            "type": "custom-title",
            "customTitle": "my-session",
            "sessionId": "abc",
        }
        transcript.write_text(json.dumps(rename_entry) + "\n")
        tokens, model, custom_title = _get_usage_from_transcript(str(transcript))
        assert custom_title == "my-session"

    def test_latest_custom_title_wins(self, tmp_path):
        """When /rename is called multiple times, the last title wins."""
        transcript = tmp_path / "transcript.jsonl"
        first_rename = {
            "type": "custom-title",
            "customTitle": "first-name",
            "sessionId": "abc",
        }
        second_rename = {
            "type": "custom-title",
            "customTitle": "final-name",
            "sessionId": "abc",
        }
        transcript.write_text(
            json.dumps(first_rename) + "\n" + json.dumps(second_rename) + "\n"
        )
        tokens, model, custom_title = _get_usage_from_transcript(str(transcript))
        assert custom_title == "final-name"

    def test_cached_title_skips_full_scan(self, tmp_path):
        """When a cached title exists, full scan is skipped; tail entry wins."""
        transcript = tmp_path / "transcript.jsonl"
        rename_entry = {
            "type": "custom-title",
            "customTitle": "new-name",
            "sessionId": "abc",
        }
        transcript.write_text(json.dumps(rename_entry) + "\n")
        _, _, custom_title = _get_usage_from_transcript(
            str(transcript), existing_custom_title="old-name"
        )
        # Entry is in the tail, so it overwrites the cached value
        assert custom_title == "new-name"

    def test_cached_title_preserved_when_no_entry(self, tmp_path):
        """When no custom-title entry exists, cached value is preserved."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(json.dumps({"type": "text"}) + "\n")
        _, _, custom_title = _get_usage_from_transcript(
            str(transcript), existing_custom_title="cached-name"
        )
        assert custom_title == "cached-name"


# ---------------------------------------------------------------------------
# _log
# ---------------------------------------------------------------------------


class TestLog:
    def test_writes_correct_format(self, tmp_path, monkeypatch):
        log_file = tmp_path / "activity.log"
        monkeypatch.setattr("flaude.hooks.dispatcher.ACTIVITY_LOG", log_file)
        _log("abcdef12-3456-7890", "PreToolUse", 'Read "foo.py"')
        content = log_file.read_text()
        assert "[abcdef12]" in content
        assert "PreToolUse" in content
        assert 'Read "foo.py"' in content

    def test_truncates_session_id(self, tmp_path, monkeypatch):
        log_file = tmp_path / "activity.log"
        monkeypatch.setattr("flaude.hooks.dispatcher.ACTIVITY_LOG", log_file)
        _log("abcdef1234567890", "Stop")
        content = log_file.read_text()
        assert "[abcdef12]" in content

    def test_empty_session_id(self, tmp_path, monkeypatch):
        log_file = tmp_path / "activity.log"
        monkeypatch.setattr("flaude.hooks.dispatcher.ACTIVITY_LOG", log_file)
        _log("", "ERROR", "something broke")
        content = log_file.read_text()
        assert "[????????]" in content

    def test_never_raises(self, monkeypatch):
        """_log must swallow all exceptions."""
        monkeypatch.setattr(
            "flaude.hooks.dispatcher.ACTIVITY_LOG", "/nonexistent/path/log"
        )
        _log("test", "Error", "this should not raise")  # no exception


# ---------------------------------------------------------------------------
# Event handlers (integration with real StateManager)
# ---------------------------------------------------------------------------


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TestHandleSessionStart:
    def test_creates_new_session(self, mgr):
        event = {"session_id": "s1", "cwd": "/tmp/proj", "permission_mode": "plan"}
        _handle_session_start(event, mgr)
        state = mgr.load_session("s1")
        assert state is not None
        assert state.status == SessionStatus.NEW
        assert state.cwd == "/tmp/proj"
        assert state.permission_mode == "plan"


class TestHandlePreToolUse:
    def test_sets_working_and_records_tool(self, mgr, no_rules):
        event = {
            "session_id": "s2",
            "cwd": "/tmp",
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/foo.py"},
        }
        _handle_pre_tool_use(event, mgr)
        state = mgr.load_session("s2")
        assert state.status == SessionStatus.WORKING
        assert state.tool_stats["Read"] == 1
        assert state.last_tool.name == "Read"
        assert state.last_tool.summary == "foo.py"

    def test_ask_user_question_sets_waiting(self, mgr, no_rules):
        question = {"questions": [{"question": "Which approach?"}]}
        event = {
            "session_id": "s3",
            "cwd": "/tmp",
            "tool_name": "AskUserQuestion",
            "tool_input": question,
        }
        _handle_pre_tool_use(event, mgr)
        state = mgr.load_session("s3")
        assert state.status == SessionStatus.WAITING_ANSWER
        assert state.pending_question == question

    def test_exit_plan_mode_sets_plan(self, mgr, no_rules):
        plan_input = {"allowedPrompts": [{"tool": "Bash", "prompt": "run tests"}]}
        event = {
            "session_id": "s3b",
            "cwd": "/tmp",
            "tool_name": "ExitPlanMode",
            "tool_input": plan_input,
        }
        _handle_pre_tool_use(event, mgr)
        state = mgr.load_session("s3b")
        assert state.status == SessionStatus.PLAN
        assert state.pending_question == plan_input

    def test_tool_stats_accumulate(self, mgr, no_rules):
        """Multiple PreToolUse events for the same tool increment the counter."""
        for _ in range(3):
            _handle_pre_tool_use(
                {
                    "session_id": "acc",
                    "cwd": "/tmp",
                    "tool_name": "Bash",
                    "tool_input": {"command": "ls"},
                },
                mgr,
            )
        state = mgr.load_session("acc")
        assert state.tool_stats["Bash"] == 3


class TestHandlePostToolUse:
    def test_clears_pending_question(self, mgr):
        state = make_state(
            "s4", pending_question={"q": "?"}, status=SessionStatus.WAITING_ANSWER
        )
        mgr.save_session(state)

        event = {"session_id": "s4", "cwd": "/tmp", "tool_name": "Read"}
        _handle_post_tool_use(event, mgr)
        state = mgr.load_session("s4")
        assert state.pending_question is None


class TestHandleStop:
    def test_sets_idle_and_clears_question(self, mgr):
        state = make_state(
            "s5", status=SessionStatus.WORKING, pending_question={"q": "?"}
        )
        mgr.save_session(state)

        _handle_stop({"session_id": "s5", "cwd": "/tmp"}, mgr)
        state = mgr.load_session("s5")
        assert state.status == SessionStatus.IDLE
        assert state.pending_question is None

    def test_calculates_turn_duration(self, mgr):
        earlier = _now() - timedelta(seconds=45)
        state = make_state("s6", status=SessionStatus.WORKING, turn_started_at=earlier)
        mgr.save_session(state)

        _handle_stop({"session_id": "s6", "cwd": "/tmp"}, mgr)
        state = mgr.load_session("s6")
        assert state.last_turn_duration >= 44  # allow for clock skew
        assert state.turn_started_at is None

    def test_updates_custom_title_from_transcript(self, mgr, tmp_path):
        transcript = tmp_path / "session.jsonl"
        rename_entry = {
            "type": "custom-title",
            "customTitle": "my-session",
            "sessionId": "ct-sess",
        }
        transcript.write_text(json.dumps(rename_entry) + "\n")

        state = make_state("ct-sess", transcript_path=str(transcript))
        mgr.save_session(state)

        _handle_stop({"session_id": "ct-sess", "cwd": "/tmp"}, mgr)
        state = mgr.load_session("ct-sess")
        assert state.custom_title == "my-session"


class TestHandlePermissionRequest:
    def test_sets_waiting_permission(self, mgr):
        state = make_state("s7b", status=SessionStatus.WORKING)
        mgr.save_session(state)

        _handle_permission_request(
            {
                "session_id": "s7b",
                "cwd": "/tmp",
                "tool_name": "Bash",
            },
            mgr,
        )
        state = mgr.load_session("s7b")
        assert state.status == SessionStatus.WAITING_PERMISSION
        assert state.last_event == "PermissionRequest"


class TestHandleUserPromptSubmit:
    def test_sets_working_and_stores_prompt(self, mgr):
        state = make_state("s9", status=SessionStatus.IDLE, pending_question={"q": "?"})
        mgr.save_session(state)

        _handle_user_prompt_submit(
            {"session_id": "s9", "cwd": "/tmp", "user_prompt": "Fix the bug"}, mgr
        )
        state = mgr.load_session("s9")
        assert state.status == SessionStatus.WORKING
        assert state.last_prompt == "Fix the bug"
        assert state.pending_question is None

    def test_truncates_long_prompt(self, mgr):
        long_prompt = "x" * 300
        state = make_state("s9b", status=SessionStatus.IDLE)
        mgr.save_session(state)

        _handle_user_prompt_submit(
            {"session_id": "s9b", "cwd": "/tmp", "user_prompt": long_prompt}, mgr
        )
        state = mgr.load_session("s9b")
        assert len(state.last_prompt) == 200

    def test_empty_prompt_preserves_existing(self, mgr):
        state = make_state(
            "s9c", status=SessionStatus.IDLE, last_prompt="previous prompt"
        )
        mgr.save_session(state)

        _handle_user_prompt_submit(
            {"session_id": "s9c", "cwd": "/tmp", "user_prompt": ""}, mgr
        )
        state = mgr.load_session("s9c")
        assert state.last_prompt == "previous prompt"


class TestHandleSubagentStop:
    def test_decrements_count(self, mgr):
        state = make_state("s10", subagent_count=3)
        mgr.save_session(state)

        _handle_subagent_stop({"session_id": "s10", "cwd": "/tmp"}, mgr)
        state = mgr.load_session("s10")
        assert state.subagent_count == 2

    def test_does_not_go_below_zero(self, mgr):
        state = make_state("s11", subagent_count=0)
        mgr.save_session(state)

        _handle_subagent_stop({"session_id": "s11", "cwd": "/tmp"}, mgr)
        state = mgr.load_session("s11")
        assert state.subagent_count == 0


class TestHandleSessionEnd:
    def test_deletes_session(self, mgr):
        state = make_state("s12")
        mgr.save_session(state)
        assert mgr.load_session("s12") is not None

        _handle_session_end({"session_id": "s12"}, mgr)
        assert mgr.load_session("s12") is None


# ---------------------------------------------------------------------------
# _load_or_create
# ---------------------------------------------------------------------------


class TestLoadOrCreate:
    def test_creates_when_missing(self, mgr):
        event = {
            "session_id": "new-sess",
            "cwd": "/tmp/proj",
            "transcript_path": "/t.jsonl",
        }
        state = _load_or_create(event, mgr)
        assert state.session_id == "new-sess"
        assert state.cwd == "/tmp/proj"
        assert state.transcript_path == "/t.jsonl"

    def test_loads_existing(self, mgr):
        existing = make_state("existing", cwd="/old")
        mgr.save_session(existing)

        event = {"session_id": "existing", "cwd": "/new"}
        state = _load_or_create(event, mgr)
        assert state.cwd == "/new"  # updated from event

    def test_backfills_transcript_path(self, mgr):
        existing = make_state("bf", transcript_path=None)
        mgr.save_session(existing)

        event = {"session_id": "bf", "transcript_path": "/new/path.jsonl"}
        state = _load_or_create(event, mgr)
        assert state.transcript_path == "/new/path.jsonl"

    def test_updates_permission_mode(self, mgr):
        existing = make_state("pm", permission_mode="default")
        mgr.save_session(existing)

        event = {"session_id": "pm", "permission_mode": "plan"}
        state = _load_or_create(event, mgr)
        assert state.permission_mode == "plan"


# ---------------------------------------------------------------------------
# Cron/loop capture
# ---------------------------------------------------------------------------


class TestCronCreateCapture:
    def test_stores_loop_from_post_tool_use(self, mgr, no_rules):
        """PostToolUse CronCreate with tool_response creates a LoopInfo."""
        state = make_state("cron-create")
        mgr.save_session(state)

        _handle_post_tool_use(
            {
                "session_id": "cron-create",
                "hook_event_name": "PostToolUse",
                "tool_name": "CronCreate",
                "tool_input": {
                    "cron": "*/5 * * * *",
                    "prompt": "check deploy",
                    "recurring": True,
                },
                "tool_response": {
                    "id": "abcd1234",
                    "humanSchedule": "Every 5 minutes",
                    "recurring": True,
                    "durable": False,
                },
            },
            mgr,
        )
        loaded = mgr.load_session("cron-create")
        assert "abcd1234" in loaded.loops
        loop = loaded.loops["abcd1234"]
        assert loop.cron_expr == "*/5 * * * *"
        assert loop.human_schedule == "Every 5 minutes"
        assert loop.prompt == "check deploy"
        assert loop.recurring is True

    def test_ignores_missing_id(self, mgr, no_rules):
        """CronCreate with empty tool_response doesn't crash."""
        state = make_state("cron-noid")
        mgr.save_session(state)

        _handle_post_tool_use(
            {
                "session_id": "cron-noid",
                "hook_event_name": "PostToolUse",
                "tool_name": "CronCreate",
                "tool_input": {"cron": "*/5 * * * *", "prompt": "test"},
                "tool_response": {},
            },
            mgr,
        )
        loaded = mgr.load_session("cron-noid")
        assert loaded.loops == {}

    def test_handles_string_tool_response(self, mgr, no_rules):
        """If tool_response is a string (unexpected), don't crash."""
        state = make_state("cron-str")
        mgr.save_session(state)

        _handle_post_tool_use(
            {
                "session_id": "cron-str",
                "hook_event_name": "PostToolUse",
                "tool_name": "CronCreate",
                "tool_input": {"cron": "*/5 * * * *", "prompt": "test"},
                "tool_response": "Scheduled recurring job abcd1234",
            },
            mgr,
        )
        loaded = mgr.load_session("cron-str")
        assert loaded.loops == {}


class TestCronDeleteCapture:
    def test_removes_loop(self, mgr, no_rules):
        loop = LoopInfo(
            task_id="abcd1234",
            cron_expr="*/5 * * * *",
            human_schedule="Every 5 minutes",
            prompt="check",
            recurring=True,
            created_at="2026-03-08T12:00:00",
        )
        state = make_state("cron-del", loops={"abcd1234": loop})
        mgr.save_session(state)

        _handle_post_tool_use(
            {
                "session_id": "cron-del",
                "hook_event_name": "PostToolUse",
                "tool_name": "CronDelete",
                "tool_response": {"id": "abcd1234"},
            },
            mgr,
        )
        loaded = mgr.load_session("cron-del")
        assert "abcd1234" not in loaded.loops

    def test_delete_nonexistent_is_noop(self, mgr, no_rules):
        state = make_state("cron-del-noop")
        mgr.save_session(state)

        _handle_post_tool_use(
            {
                "session_id": "cron-del-noop",
                "hook_event_name": "PostToolUse",
                "tool_name": "CronDelete",
                "tool_response": {"id": "nonexist"},
            },
            mgr,
        )
        loaded = mgr.load_session("cron-del-noop")
        assert loaded.loops == {}


class TestCronListReconcile:
    def test_replaces_loops_with_active_jobs(self, mgr, no_rules):
        """CronList reconciles: replaces loops dict with what's actually active."""
        old_loop = LoopInfo(
            task_id="old11111",
            cron_expr="*/10 * * * *",
            human_schedule="Every 10 minutes",
            prompt="old job",
            recurring=True,
            created_at="2026-03-08T10:00:00",
        )
        state = make_state("cron-list", loops={"old11111": old_loop})
        mgr.save_session(state)

        _handle_post_tool_use(
            {
                "session_id": "cron-list",
                "hook_event_name": "PostToolUse",
                "tool_name": "CronList",
                "tool_response": {
                    "jobs": [
                        {
                            "id": "new22222",
                            "cron": "*/2 * * * *",
                            "humanSchedule": "Every 2 minutes",
                            "prompt": "new job",
                            "recurring": True,
                            "durable": False,
                        }
                    ]
                },
            },
            mgr,
        )
        loaded = mgr.load_session("cron-list")
        assert "old11111" not in loaded.loops
        assert "new22222" in loaded.loops
        assert loaded.loops["new22222"].cron_expr == "*/2 * * * *"
        assert loaded.loops["new22222"].prompt == "new job"

    def test_empty_list_clears_loops(self, mgr, no_rules):
        loop = LoopInfo(
            task_id="gone1111",
            cron_expr="*/5 * * * *",
            human_schedule="Every 5 minutes",
            prompt="expired",
            recurring=True,
            created_at="2026-03-08T10:00:00",
        )
        state = make_state("cron-list-empty", loops={"gone1111": loop})
        mgr.save_session(state)

        _handle_post_tool_use(
            {
                "session_id": "cron-list-empty",
                "hook_event_name": "PostToolUse",
                "tool_name": "CronList",
                "tool_response": {"jobs": []},
            },
            mgr,
        )
        loaded = mgr.load_session("cron-list-empty")
        assert loaded.loops == {}

    def test_preserves_created_at_from_existing(self, mgr, no_rules):
        """When CronList sees a job we already have, preserve our created_at."""
        existing = LoopInfo(
            task_id="keep1111",
            cron_expr="*/5 * * * *",
            human_schedule="Every 5 minutes",
            prompt="check",
            recurring=True,
            created_at="2026-03-08T10:00:00",
        )
        state = make_state("cron-list-keep", loops={"keep1111": existing})
        mgr.save_session(state)

        _handle_post_tool_use(
            {
                "session_id": "cron-list-keep",
                "hook_event_name": "PostToolUse",
                "tool_name": "CronList",
                "tool_response": {
                    "jobs": [
                        {
                            "id": "keep1111",
                            "cron": "*/5 * * * *",
                            "humanSchedule": "Every 5 minutes",
                            "prompt": "check",
                            "recurring": True,
                            "durable": False,
                        }
                    ]
                },
            },
            mgr,
        )
        loaded = mgr.load_session("cron-list-keep")
        assert loaded.loops["keep1111"].created_at == "2026-03-08T10:00:00"


class TestLoopLifecycle:
    """End-to-end: create session → create loop → list → delete → verify."""

    def test_full_lifecycle(self, mgr, no_rules):
        _handle_session_start({"session_id": "loop-e2e", "cwd": "/tmp/test"}, mgr)

        # Create a loop
        _handle_post_tool_use(
            {
                "session_id": "loop-e2e",
                "hook_event_name": "PostToolUse",
                "tool_name": "CronCreate",
                "tool_input": {
                    "cron": "*/5 * * * *",
                    "prompt": "check deploy",
                    "recurring": True,
                },
                "tool_response": {
                    "id": "aaaa1111",
                    "humanSchedule": "Every 5 minutes",
                    "recurring": True,
                    "durable": False,
                },
            },
            mgr,
        )

        state = mgr.load_session("loop-e2e")
        assert "aaaa1111" in state.loops
        assert state.loops["aaaa1111"].prompt == "check deploy"

        # CronList confirms the loop
        _handle_post_tool_use(
            {
                "session_id": "loop-e2e",
                "hook_event_name": "PostToolUse",
                "tool_name": "CronList",
                "tool_response": {
                    "jobs": [
                        {
                            "id": "aaaa1111",
                            "cron": "*/5 * * * *",
                            "humanSchedule": "Every 5 minutes",
                            "prompt": "check deploy",
                            "recurring": True,
                            "durable": False,
                        }
                    ]
                },
            },
            mgr,
        )

        state = mgr.load_session("loop-e2e")
        assert len(state.loops) == 1

        # Delete the loop
        _handle_post_tool_use(
            {
                "session_id": "loop-e2e",
                "hook_event_name": "PostToolUse",
                "tool_name": "CronDelete",
                "tool_response": {"id": "aaaa1111"},
            },
            mgr,
        )

        state = mgr.load_session("loop-e2e")
        assert len(state.loops) == 0

        # Session end cleans up
        _handle_session_end({"session_id": "loop-e2e"}, mgr)
        assert mgr.load_session("loop-e2e") is None
