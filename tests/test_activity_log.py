import json

from flaude.tui.widgets.activity_log import _format_cache_entry


class TestFormatCacheEntry:
    def test_formats_pre_tool_use(self):
        entry = {
            "ts": "2026-03-08T12:00:00",
            "ev": "PreToolUse",
            "tool": "Read",
            "sum": "foo.py",
        }
        result = _format_cache_entry(entry)
        assert "Read" in result
        assert "foo.py" in result

    def test_formats_user_prompt(self):
        entry = {"ts": "2026-03-08T12:00:00", "ev": "UserPrompt", "text": "Fix the bug"}
        result = _format_cache_entry(entry)
        assert "Fix the bug" in result

    def test_formats_stop(self):
        entry = {"ts": "2026-03-08T12:00:00", "ev": "Stop"}
        result = _format_cache_entry(entry)
        assert result is not None
        assert "idle" in result

    def test_formats_session_start(self):
        entry = {"ts": "2026-03-08T12:00:00", "ev": "SessionStart"}
        result = _format_cache_entry(entry)
        assert "session started" in result

    def test_formats_permission_request(self):
        entry = {"ts": "2026-03-08T12:00:00", "ev": "PermissionRequest", "tool": "Bash"}
        result = _format_cache_entry(entry)
        assert "permission" in result
        assert "Bash" in result

    def test_post_tool_use_returns_none(self):
        entry = {"ts": "2026-03-08T12:00:00", "ev": "PostToolUse", "tool": "Read"}
        assert _format_cache_entry(entry) is None

    def test_unknown_event_returns_none(self):
        entry = {"ts": "2026-03-08T12:00:00", "ev": "Unknown"}
        assert _format_cache_entry(entry) is None
