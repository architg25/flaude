"""Tests for the notification manager.

Covers the three retroactive-alert bugs (startup, toggle on, settings save)
and the core check/seed/clear lifecycle.
"""

from datetime import timedelta
from unittest.mock import MagicMock

from helpers import make_state
from flaude.state.models import SessionStatus
from flaude.formatting import format_duration_seconds
from flaude.tui.notifications import NotificationManager


def _config(
    enabled=True, ltc_enabled=True, ltc_minutes=5, woi_enabled=False, woi_delay=10
):
    return {
        "enabled": enabled,
        "long_turn_completion": {
            "enabled": ltc_enabled,
            "terminal_bell": False,
            "macos_alert": False,
            "system_sound": False,
            "long_turn_minutes": ltc_minutes,
        },
        "waiting_on_input": {
            "enabled": woi_enabled,
            "terminal_bell": False,
            "macos_alert": False,
            "system_sound": False,
            "delay_seconds": woi_delay,
        },
    }


# ---------------------------------------------------------------------------
# Seed — prevents retroactive alerts
# ---------------------------------------------------------------------------


class TestSeed:
    def test_seed_marks_completed_long_turns(self):
        nm = NotificationManager()
        active = {
            "s1": make_state("s1", last_turn_duration=600, turn_started_at=None),
        }
        nm.seed(active, _config(ltc_minutes=5))
        assert "s1" in nm._alerted_turns

    def test_seed_ignores_short_turns(self):
        nm = NotificationManager()
        active = {
            "s1": make_state("s1", last_turn_duration=60, turn_started_at=None),
        }
        nm.seed(active, _config(ltc_minutes=5))
        assert "s1" not in nm._alerted_turns

    def test_seed_marks_waiting_sessions(self):
        nm = NotificationManager()
        active = {
            "s1": make_state("s1", status=SessionStatus.WAITING_PERMISSION),
            "s2": make_state("s2", status=SessionStatus.PLAN),
            "s3": make_state("s3", status=SessionStatus.WORKING),
        }
        nm.seed(active, _config())
        assert "s1" in nm._alerted_waiting
        assert "s2" in nm._alerted_waiting
        assert "s3" not in nm._alerted_waiting

    def test_seed_skips_ended_sessions(self):
        nm = NotificationManager()
        active = {
            "s1": make_state("s1", status=SessionStatus.ENDED, last_turn_duration=600),
        }
        nm.seed(active, _config())
        assert "s1" not in nm._alerted_turns

    def test_seed_clears_previous_state(self):
        nm = NotificationManager()
        nm._alerted_turns.add("old-session")
        nm._alerted_waiting.add("old-session")
        nm.seed({}, _config())
        assert len(nm._alerted_turns) == 0
        assert len(nm._alerted_waiting) == 0


# ---------------------------------------------------------------------------
# Check — core notification logic
# ---------------------------------------------------------------------------


class TestCheckLongTurns:
    def test_fires_on_completed_long_turn(self):
        bell = MagicMock()
        nm = NotificationManager(bell=bell)
        active = {
            "s1": make_state(
                "s1", last_turn_duration=600, turn_started_at=None, cwd="/proj"
            ),
        }
        cfg = _config(ltc_minutes=5)
        cfg["long_turn_completion"]["terminal_bell"] = True
        nm.check(active, cfg)
        bell.assert_called_once()
        assert "s1" in nm._alerted_turns

    def test_does_not_fire_twice(self):
        bell = MagicMock()
        nm = NotificationManager(bell=bell)
        active = {
            "s1": make_state(
                "s1", last_turn_duration=600, turn_started_at=None, cwd="/proj"
            ),
        }
        cfg = _config(ltc_minutes=5)
        cfg["long_turn_completion"]["terminal_bell"] = True
        nm.check(active, cfg)
        nm.check(active, cfg)
        bell.assert_called_once()

    def test_does_not_fire_below_threshold(self):
        bell = MagicMock()
        nm = NotificationManager(bell=bell)
        active = {
            "s1": make_state(
                "s1", last_turn_duration=60, turn_started_at=None, cwd="/proj"
            ),
        }
        nm.check(active, _config(ltc_minutes=5))
        bell.assert_not_called()

    def test_does_not_fire_while_turn_active(self):
        """turn_started_at being set means the turn is still running."""
        bell = MagicMock()
        nm = NotificationManager(bell=bell)
        from flaude.constants import utcnow

        active = {
            "s1": make_state(
                "s1",
                last_turn_duration=600,
                turn_started_at=utcnow(),
                cwd="/proj",
            ),
        }
        nm.check(active, _config(ltc_minutes=5))
        bell.assert_not_called()

    def test_resets_when_new_turn_starts(self):
        """After alerting, starting a new turn should allow re-alerting later."""
        nm = NotificationManager()
        nm._alerted_turns.add("s1")
        from flaude.constants import utcnow

        active = {
            "s1": make_state("s1", turn_started_at=utcnow(), cwd="/proj"),
        }
        nm.check(active, _config(ltc_minutes=5))
        assert "s1" not in nm._alerted_turns

    def test_does_not_fire_when_disabled(self):
        bell = MagicMock()
        nm = NotificationManager(bell=bell)
        active = {
            "s1": make_state(
                "s1", last_turn_duration=600, turn_started_at=None, cwd="/proj"
            ),
        }
        nm.check(active, _config(enabled=False))
        bell.assert_not_called()

    def test_does_not_fire_when_category_disabled(self):
        bell = MagicMock()
        nm = NotificationManager(bell=bell)
        active = {
            "s1": make_state(
                "s1", last_turn_duration=600, turn_started_at=None, cwd="/proj"
            ),
        }
        nm.check(active, _config(ltc_enabled=False))
        bell.assert_not_called()


class TestCheckWaiting:
    def test_fires_after_delay(self):
        bell = MagicMock()
        nm = NotificationManager(bell=bell)
        cfg = _config(woi_enabled=True, woi_delay=0)
        cfg["waiting_on_input"]["terminal_bell"] = True

        active = {
            "s1": make_state(
                "s1", status=SessionStatus.WAITING_PERMISSION, cwd="/proj"
            ),
        }
        # First check: records the timestamp
        nm.check(active, cfg)
        # Second check: delay=0 means fire immediately
        nm.check(active, cfg)
        bell.assert_called_once()
        assert "s1" in nm._alerted_waiting

    def test_does_not_fire_before_delay(self):
        bell = MagicMock()
        nm = NotificationManager(bell=bell)
        cfg = _config(woi_enabled=True, woi_delay=9999)
        cfg["waiting_on_input"]["terminal_bell"] = True

        active = {
            "s1": make_state(
                "s1", status=SessionStatus.WAITING_PERMISSION, cwd="/proj"
            ),
        }
        nm.check(active, cfg)
        nm.check(active, cfg)
        bell.assert_not_called()

    def test_clears_when_no_longer_waiting(self):
        nm = NotificationManager()
        nm._alerted_waiting.add("s1")
        nm._waiting_entered_at["s1"] = make_state("s1").started_at

        active = {
            "s1": make_state("s1", status=SessionStatus.WORKING, cwd="/proj"),
        }
        nm.check(active, _config(woi_enabled=True))
        assert "s1" not in nm._alerted_waiting
        assert "s1" not in nm._waiting_entered_at


# ---------------------------------------------------------------------------
# Prune — memory leak prevention
# ---------------------------------------------------------------------------


class TestPrune:
    def test_removes_ended_sessions(self):
        nm = NotificationManager()
        nm._alerted_turns.update({"s1", "s2"})
        nm._alerted_waiting.update({"s1", "s3"})
        nm._waiting_entered_at["s3"] = make_state("s3").started_at

        # Only s1 is still active
        active = {"s1": make_state("s1", cwd="/proj")}
        nm.check(active, _config())

        assert nm._alerted_turns == {"s1"}
        assert nm._alerted_waiting == {"s1"}
        assert "s3" not in nm._waiting_entered_at


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clears_everything(self):
        nm = NotificationManager()
        nm._alerted_turns.add("s1")
        nm._alerted_waiting.add("s2")
        nm._waiting_entered_at["s2"] = make_state("s2").started_at
        nm.clear()
        assert len(nm._alerted_turns) == 0
        assert len(nm._alerted_waiting) == 0
        assert len(nm._waiting_entered_at) == 0


# ---------------------------------------------------------------------------
# _format_duration
# ---------------------------------------------------------------------------


class TestFormatDuration:
    def test_minutes(self):
        assert format_duration_seconds(300) == "5m"

    def test_hours(self):
        assert format_duration_seconds(3900) == "1h5m"

    def test_zero(self):
        assert format_duration_seconds(0) == "0m"
