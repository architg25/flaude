"""Tests for tool-input summarization helpers."""

import pytest

from flaude.tools import basename, summarize_tool, trunc


# ---------------------------------------------------------------------------
# trunc
# ---------------------------------------------------------------------------


class TestTrunc:
    def test_empty_string(self):
        assert trunc("", 10) == ""

    def test_short_string(self):
        assert trunc("hello", 10) == "hello"

    def test_exact_length(self):
        assert trunc("hello", 5) == "hello"

    def test_long_string(self):
        assert trunc("hello world", 5) == "hello..."

    def test_n_zero(self):
        assert trunc("hello", 0) == "..."

    def test_n_zero_empty(self):
        assert trunc("", 0) == ""


# ---------------------------------------------------------------------------
# basename
# ---------------------------------------------------------------------------


class TestBasename:
    def test_simple_path(self):
        assert basename("/foo/bar.py") == "bar.py"

    def test_nested_path(self):
        assert basename("/a/b/c/d/file.txt") == "file.txt"

    def test_no_slashes(self):
        assert basename("file.txt") == "file.txt"

    def test_empty(self):
        assert basename("") == ""


# ---------------------------------------------------------------------------
# summarize_tool
# ---------------------------------------------------------------------------


class TestSummarizeTool:
    def test_bash(self):
        result = summarize_tool("Bash", {"command": "ls -la"})
        assert result == "ls -la"

    def test_bash_long_command_truncated(self):
        cmd = "x" * 100
        result = summarize_tool("Bash", {"command": cmd})
        assert result == "x" * 80 + "..."

    def test_bash_empty_input(self):
        assert summarize_tool("Bash", {}) == ""

    def test_read(self):
        result = summarize_tool("Read", {"file_path": "/src/flaude/tools.py"})
        assert result == "tools.py"

    def test_edit(self):
        result = summarize_tool("Edit", {"file_path": "/a/b/c.py"})
        assert result == "c.py"

    def test_multi_edit(self):
        result = summarize_tool("MultiEdit", {"file_path": "/a/b/c.py"})
        assert result == "c.py"

    def test_write(self):
        result = summarize_tool("Write", {"file_path": "/tmp/out.json"})
        assert result == "out.json"

    def test_grep(self):
        result = summarize_tool("Grep", {"pattern": "def foo"})
        assert result == "def foo"

    def test_grep_long_pattern_truncated(self):
        pat = "a" * 50
        result = summarize_tool("Grep", {"pattern": pat})
        assert result == "a" * 40 + "..."

    def test_glob(self):
        result = summarize_tool("Glob", {"pattern": "**/*.py"})
        assert result == "**/*.py"

    def test_task(self):
        result = summarize_tool("Task", {"prompt": "Do the thing"})
        assert result == "Do the thing"

    def test_web_fetch(self):
        result = summarize_tool("WebFetch", {"url": "https://example.com"})
        assert result == "https://example.com"

    def test_unknown_tool_returns_name(self):
        result = summarize_tool("SomeNewTool", {"foo": "bar"})
        assert result == "SomeNewTool"
