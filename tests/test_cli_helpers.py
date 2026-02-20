"""Tests for CLI pure helper functions."""

from datetime import datetime, timedelta

import pytest

from flaude.cli import (
    _build_hook_entry,
    _format_context,
    _format_uptime,
    _is_flaude_hook,
)


# ---------------------------------------------------------------------------
# _format_uptime
# ---------------------------------------------------------------------------


class TestFormatUptime:
    def test_seconds(self):
        started = datetime.now() - timedelta(seconds=42)
        assert _format_uptime(started) == "42s"

    def test_minutes_and_seconds(self):
        started = datetime.now() - timedelta(minutes=3, seconds=15)
        assert _format_uptime(started) == "3m15s"

    def test_hours_and_minutes(self):
        started = datetime.now() - timedelta(hours=2, minutes=30, seconds=5)
        assert _format_uptime(started) == "2h30m"


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
        entry = _build_hook_entry()
        assert entry["matcher"] == ""
        assert len(entry["hooks"]) == 1
        hook = entry["hooks"][0]
        assert hook["type"] == "command"
        assert "flaude" in hook["command"]

    def test_is_flaude_hook_true(self):
        entry = _build_hook_entry()
        assert _is_flaude_hook(entry) is True

    def test_is_flaude_hook_false(self):
        entry = {"hooks": [{"type": "command", "command": "some-other-tool"}]}
        assert _is_flaude_hook(entry) is False

    def test_is_flaude_hook_no_hooks_key(self):
        assert _is_flaude_hook({}) is False
