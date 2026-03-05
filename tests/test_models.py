"""Tests for state/models.py — enums, pydantic models, and status metadata."""

from datetime import datetime, timezone

import pytest

from flaude.state.models import (
    STATUS_INFO,
    WAITING_STATUSES,
    LastTool,
    SessionState,
    SessionStatus,
    StatusInfo,
)


# ---------------------------------------------------------------------------
# SessionStatus enum
# ---------------------------------------------------------------------------


class TestSessionStatus:
    def test_all_values(self):
        expected = {
            "new",
            "working",
            "idle",
            "waiting_permission",
            "waiting_answer",
            "plan",
            "error",
            "ended",
        }
        assert {s.value for s in SessionStatus} == expected

    def test_string_representation(self):
        assert str(SessionStatus.WORKING) == "SessionStatus.WORKING"
        assert SessionStatus.IDLE.value == "idle"

    def test_is_str_subclass(self):
        # SessionStatus(str, Enum) means values are usable as strings
        assert isinstance(SessionStatus.NEW, str)
        assert SessionStatus.NEW == "new"

    def test_lookup_by_value(self):
        assert SessionStatus("error") is SessionStatus.ERROR


# ---------------------------------------------------------------------------
# StatusInfo & STATUS_INFO mapping
# ---------------------------------------------------------------------------


class TestStatusInfo:
    def test_every_status_has_info(self):
        for status in SessionStatus:
            assert status in STATUS_INFO, f"Missing STATUS_INFO entry for {status}"

    def test_no_extra_entries(self):
        for key in STATUS_INFO:
            assert key in SessionStatus, f"Extra STATUS_INFO key: {key}"

    def test_sort_priority_ordering(self):
        """Waiting/attention statuses should sort before idle/ended."""
        waiting_prio = STATUS_INFO[SessionStatus.WAITING_PERMISSION].sort_priority
        idle_prio = STATUS_INFO[SessionStatus.IDLE].sort_priority
        ended_prio = STATUS_INFO[SessionStatus.ENDED].sort_priority
        assert waiting_prio < idle_prio
        assert idle_prio < ended_prio

    def test_fields(self):
        info = STATUS_INFO[SessionStatus.ERROR]
        assert info.label == "ERROR"
        assert info.indicator == "\u2716"  # heavy ballot X
        assert info.theme_var == "error"
        assert info.bold is True
        assert isinstance(info.sort_priority, int)

    def test_frozen(self):
        info = STATUS_INFO[SessionStatus.NEW]
        with pytest.raises(AttributeError):
            info.label = "changed"


# ---------------------------------------------------------------------------
# WAITING_STATUSES
# ---------------------------------------------------------------------------


class TestWaitingStatuses:
    def test_contains_expected(self):
        assert SessionStatus.WAITING_PERMISSION in WAITING_STATUSES
        assert SessionStatus.WAITING_ANSWER in WAITING_STATUSES
        assert SessionStatus.PLAN in WAITING_STATUSES

    def test_does_not_contain_non_waiting(self):
        assert SessionStatus.WORKING not in WAITING_STATUSES
        assert SessionStatus.IDLE not in WAITING_STATUSES
        assert SessionStatus.ENDED not in WAITING_STATUSES

    def test_all_have_lowest_sort_priority(self):
        """All waiting statuses should have sort_priority 0 (highest urgency)."""
        for status in WAITING_STATUSES:
            assert STATUS_INFO[status].sort_priority == 0


# ---------------------------------------------------------------------------
# LastTool model
# ---------------------------------------------------------------------------


class TestLastTool:
    def test_creation(self):
        now = datetime.now(timezone.utc)
        tool = LastTool(name="Read", summary="read foo.py", at=now)
        assert tool.name == "Read"
        assert tool.summary == "read foo.py"
        assert tool.at == now

    def test_requires_fields(self):
        with pytest.raises(Exception):
            LastTool()


# ---------------------------------------------------------------------------
# SessionState model
# ---------------------------------------------------------------------------


class TestSessionState:
    def _now(self):
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def test_creation_with_defaults(self):
        now = self._now()
        state = SessionState(session_id="s1", started_at=now, last_event_at=now)
        assert state.session_id == "s1"
        assert state.status == SessionStatus.WORKING
        assert state.cwd == ""
        assert state.permission_mode == "default"
        assert state.tool_stats == {}
        assert state.last_tool is None
        assert state.error_count == 0

    def test_explicit_status(self):
        now = self._now()
        state = SessionState(
            session_id="s2",
            started_at=now,
            last_event_at=now,
            status=SessionStatus.IDLE,
        )
        assert state.status == SessionStatus.IDLE

    def test_extra_fields_ignored(self):
        now = self._now()
        state = SessionState(
            session_id="s3",
            started_at=now,
            last_event_at=now,
            bogus_field="surprise",
        )
        assert not hasattr(state, "bogus_field")

    def test_tool_stats(self):
        now = self._now()
        state = SessionState(
            session_id="s4",
            started_at=now,
            last_event_at=now,
            tool_stats={"Read": 5, "Write": 2},
        )
        assert state.tool_stats["Read"] == 5

    def test_with_last_tool(self):
        now = self._now()
        tool = LastTool(name="Bash", summary="run tests", at=now)
        state = SessionState(
            session_id="s5",
            started_at=now,
            last_event_at=now,
            last_tool=tool,
        )
        assert state.last_tool.name == "Bash"

    def test_missing_required_field_raises(self):
        with pytest.raises(Exception):
            SessionState(status=SessionStatus.IDLE)
