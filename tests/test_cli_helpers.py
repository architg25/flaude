"""Tests for CLI pure helper functions."""

from datetime import datetime, timedelta

from flaude.cli import (
    _build_hook_entry,
    _format_context,
    _is_flaude_hook,
)
from flaude.formatting import format_uptime, format_compact_duration


# ---------------------------------------------------------------------------
# format_uptime (shared)
# ---------------------------------------------------------------------------


class TestFormatUptime:
    def test_minutes(self):
        now = datetime.now()
        started = now - timedelta(minutes=42, seconds=10)
        assert format_uptime(now, started) == "42m"

    def test_hours_and_minutes(self):
        now = datetime.now()
        started = now - timedelta(hours=2, minutes=30)
        assert format_uptime(now, started) == "2h30m"

    def test_days_and_hours(self):
        now = datetime.now()
        started = now - timedelta(days=1, hours=3)
        assert format_uptime(now, started) == "1d3h"


class TestFormatCompactDuration:
    def test_seconds(self):
        now = datetime.now()
        since = now - timedelta(seconds=42)
        assert format_compact_duration(now, since) == "42s"

    def test_minutes_and_seconds(self):
        now = datetime.now()
        since = now - timedelta(minutes=3, seconds=5)
        assert format_compact_duration(now, since) == "3m05s"

    def test_hours_and_minutes(self):
        now = datetime.now()
        since = now - timedelta(hours=1, minutes=30)
        assert format_compact_duration(now, since) == "1h30m"

    def test_clamps_negative_to_zero(self):
        now = datetime.now()
        future = now + timedelta(seconds=5)
        assert format_compact_duration(now, future) == "0s"


# ---------------------------------------------------------------------------
# _format_context
# ---------------------------------------------------------------------------


class TestFormatContext:
    def test_zero_tokens(self):
        assert _format_context(0, None) == "-"

    def test_small_tokens(self):
        assert _format_context(500, None) == "500 (0%)"

    def test_k_formatting(self):
        result = _format_context(50_000, None)
        assert result == "50K (25%)"

    def test_m_formatting(self):
        result = _format_context(1_500_000, "claude-opus-4-20250514")
        assert result == "1.5M (150%)"

    def test_opus_limit(self):
        # Opus has 1M context — 500K should be 50%
        result = _format_context(500_000, "claude-opus-4-20250514")
        assert "50%" in result

    def test_sonnet_limit(self):
        # Sonnet has 200K — 100K should be 50%
        result = _format_context(100_000, "claude-sonnet-4-20250514")
        assert "50%" in result

    def test_unknown_model_uses_default(self):
        # Default is 200K — 100K should be 50%
        result = _format_context(100_000, "some-unknown-model")
        assert "50%" in result


# ---------------------------------------------------------------------------
# _build_hook_entry / _is_flaude_hook
# ---------------------------------------------------------------------------


class TestHookHelpers:
    def test_build_hook_entry_structure(self):
        entry = _build_hook_entry("flaude-hook")
        assert entry["matcher"] == ""
        assert len(entry["hooks"]) == 1
        hook = entry["hooks"][0]
        assert hook["type"] == "command"
        assert "flaude" in hook["command"]

    def test_is_flaude_hook_true(self):
        entry = _build_hook_entry("flaude-hook")
        assert _is_flaude_hook(entry) is True

    def test_is_flaude_hook_false(self):
        entry = {"hooks": [{"type": "command", "command": "some-other-tool"}]}
        assert _is_flaude_hook(entry) is False

    def test_is_flaude_hook_no_hooks_key(self):
        assert _is_flaude_hook({}) is False
