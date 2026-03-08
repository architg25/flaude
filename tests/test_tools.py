"""Tests for tool-input summarization — the TUI-visible summaries."""

import pytest

from flaude.tools import summarize_tool


class TestSummarizeTool:
    """Each tool type produces a short display string for the dashboard."""

    def test_bash(self):
        assert summarize_tool("Bash", {"command": "ls -la"}) == "ls -la"

    def test_bash_long_command_truncated(self):
        cmd = "x" * 100
        result = summarize_tool("Bash", {"command": cmd})
        assert result == "x" * 80 + "..."

    def test_read(self):
        assert (
            summarize_tool("Read", {"file_path": "/src/flaude/tools.py"}) == "tools.py"
        )

    def test_edit(self):
        assert summarize_tool("Edit", {"file_path": "/a/b/c.py"}) == "c.py"

    def test_multi_edit(self):
        assert summarize_tool("MultiEdit", {"file_path": "/a/b/c.py"}) == "c.py"

    def test_write(self):
        assert summarize_tool("Write", {"file_path": "/tmp/out.json"}) == "out.json"

    def test_grep(self):
        assert summarize_tool("Grep", {"pattern": "def foo"}) == "def foo"

    def test_grep_long_pattern_truncated(self):
        pat = "a" * 50
        result = summarize_tool("Grep", {"pattern": pat})
        assert result == "a" * 40 + "..."

    def test_glob(self):
        assert summarize_tool("Glob", {"pattern": "**/*.py"}) == "**/*.py"

    def test_task(self):
        assert summarize_tool("Task", {"prompt": "Do the thing"}) == "Do the thing"

    def test_web_fetch(self):
        assert (
            summarize_tool("WebFetch", {"url": "https://example.com"})
            == "https://example.com"
        )

    def test_unknown_tool_returns_name(self):
        assert summarize_tool("SomeNewTool", {"foo": "bar"}) == "SomeNewTool"

    @pytest.mark.parametrize(
        "tool", ["Bash", "Read", "Grep", "Glob", "Task", "WebFetch"]
    )
    def test_missing_keys_return_empty(self, tool):
        """Summarizers handle empty dicts gracefully."""
        assert summarize_tool(tool, {}) == ""


class TestCronSummarizers:
    def test_cron_create(self):
        result = summarize_tool(
            "CronCreate",
            {
                "cron": "*/5 * * * *",
                "prompt": "check if the deploy finished",
            },
        )
        assert "*/5 * * * *" in result
        assert "check if the deploy" in result

    def test_cron_create_missing_fields(self):
        assert summarize_tool("CronCreate", {}) == ""

    def test_cron_delete(self):
        result = summarize_tool("CronDelete", {"id": "abcd1234"})
        assert result == "abcd1234"

    def test_cron_delete_missing_id(self):
        assert summarize_tool("CronDelete", {}) == ""

    def test_cron_list_falls_through(self):
        """CronList has no summarizer — returns tool name."""
        assert summarize_tool("CronList", {}) == "CronList"
