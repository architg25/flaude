"""Tests for hooks/dispatcher.py — tool summarization, terminal detection,
transcript parsing, and event handlers."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from helpers import make_state
from flaude.hooks.dispatcher import (
    _basename,
    _detect_terminal_from_env,
    _get_usage_from_transcript,
    _handle_notification,
    _handle_post_tool_use,
    _handle_pre_tool_use,
    _handle_session_end,
    _handle_session_start,
    _handle_stop,
    _handle_subagent_stop,
    _handle_user_prompt_submit,
    _load_or_create,
    _log,
    _summarize_tool,
    _trunc,
)
from flaude.state.models import SessionStatus


# ---------------------------------------------------------------------------
# _trunc / _basename
# ---------------------------------------------------------------------------


class TestTrunc:
    def test_short_string_no_ellipsis(self):
        assert _trunc("hello", 10) == "hello"

    def test_exact_length_no_ellipsis(self):
        assert _trunc("hello", 5) == "hello"

    def test_long_string_adds_ellipsis(self):
        assert _trunc("hello world", 5) == "hello..."

    def test_empty_string(self):
        assert _trunc("", 10) == ""


class TestBasename:
    def test_full_path(self):
        assert _basename("/home/user/project/foo.py") == "foo.py"

    def test_empty_string(self):
        assert _basename("") == ""

    def test_just_filename(self):
        assert _basename("foo.py") == "foo.py"


# ---------------------------------------------------------------------------
# _summarize_tool
# ---------------------------------------------------------------------------


class TestSummarizeTool:
    def test_bash_truncates_command(self):
        cmd = "x" * 100
        result = _summarize_tool("Bash", {"command": cmd})
        assert result == cmd[:80] + "..."

    def test_bash_short_command(self):
        assert _summarize_tool("Bash", {"command": "ls"}) == "ls"

    @pytest.mark.parametrize("tool", ["Edit", "Write", "Read"])
    def test_file_tools_extract_basename(self, tool):
        result = _summarize_tool(tool, {"file_path": "/home/user/project/main.py"})
        assert result == "main.py"

    def test_grep_truncates_pattern(self):
        pat = "a" * 50
        result = _summarize_tool("Grep", {"pattern": pat})
        assert result == pat[:40] + "..."

    def test_glob_returns_pattern(self):
        assert _summarize_tool("Glob", {"pattern": "**/*.py"}) == "**/*.py"

    def test_task_truncates_prompt(self):
        prompt = "p" * 80
        result = _summarize_tool("Task", {"prompt": prompt})
        assert result == prompt[:60] + "..."

    def test_webfetch_truncates_url(self):
        url = "https://example.com/" + "x" * 60
        result = _summarize_tool("WebFetch", {"url": url})
        assert len(result) == 63  # 60 + "..."

    def test_unknown_tool_returns_name(self):
        assert _summarize_tool("SomeFancyTool", {"whatever": 1}) == "SomeFancyTool"

    @pytest.mark.parametrize(
        "tool,expected",
        [
            ("Bash", ""),
            ("Read", ""),
            ("Grep", ""),
            ("Glob", ""),
            ("Task", ""),
            ("WebFetch", ""),
        ],
    )
    def test_missing_keys_return_empty(self, tool, expected):
        """Summarizers handle empty dicts gracefully."""
        result = _summarize_tool(tool, {})
        assert result == expected


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
        assert _get_usage_from_transcript(None) == (0, None)

    def test_missing_file(self, tmp_path):
        assert _get_usage_from_transcript(str(tmp_path / "nope.jsonl")) == (0, None)

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
        tokens, model = _get_usage_from_transcript(str(transcript))
        assert tokens == 6200
        assert model == "claude-sonnet-4-20250514"

    def test_no_usage_entries(self, tmp_path):
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(json.dumps({"type": "text"}) + "\n")
        assert _get_usage_from_transcript(str(transcript)) == (0, None)

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
        tokens, model = _get_usage_from_transcript(str(transcript))
        assert tokens == 500
        assert model == "opus"

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
        tokens, model = _get_usage_from_transcript(str(transcript))
        assert tokens == 999
        assert model == "new-model"


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


class TestHandleNotification:
    def test_permission_notification(self, mgr):
        state = make_state("s7")
        mgr.save_session(state)

        _handle_notification(
            {
                "session_id": "s7",
                "cwd": "/tmp",
                "message": "Tool requires permission approval",
            },
            mgr,
        )
        state = mgr.load_session("s7")
        assert state.status == SessionStatus.WAITING_PERMISSION

    def test_attention_notification(self, mgr):
        state = make_state("s8")
        mgr.save_session(state)

        _handle_notification(
            {
                "session_id": "s8",
                "cwd": "/tmp",
                "message": "Claude needs your attention",
            },
            mgr,
        )
        state = mgr.load_session("s8")
        assert state.status == SessionStatus.WAITING_ANSWER


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
