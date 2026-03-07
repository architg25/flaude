"""Tests for terminal detection, launch script generation, and text injection."""

import subprocess
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# detect.py — terminal detection
# ---------------------------------------------------------------------------


class TestDetectTerminal:
    """Tests for detect_terminal() via osascript process list."""

    def test_known_terminal_iterm2(self, monkeypatch):
        mock_result = MagicMock()
        mock_result.stdout = "Finder, Dock, iTerm2, Spotlight\n"
        monkeypatch.setattr(
            "flaude.terminal.detect.subprocess.run", lambda *a, **kw: mock_result
        )
        monkeypatch.setattr("flaude.terminal.detect.TERMINAL_OVERRIDE", None)

        from flaude.terminal.detect import detect_terminal

        assert detect_terminal() == "iTerm2"

    def test_known_terminal_preference_order(self, monkeypatch):
        """When multiple terminals are running, first in KNOWN_TERMINALS list wins."""
        mock_result = MagicMock()
        mock_result.stdout = "Ghostty, iTerm2, Terminal\n"
        monkeypatch.setattr(
            "flaude.terminal.detect.subprocess.run", lambda *a, **kw: mock_result
        )
        monkeypatch.setattr("flaude.terminal.detect.TERMINAL_OVERRIDE", None)

        from flaude.terminal.detect import detect_terminal

        assert detect_terminal() == "iTerm2"

    def test_jetbrains_ide_detected(self, monkeypatch):
        mock_result = MagicMock()
        mock_result.stdout = "Finder, Dock, PyCharm\n"
        monkeypatch.setattr(
            "flaude.terminal.detect.subprocess.run", lambda *a, **kw: mock_result
        )
        monkeypatch.setattr("flaude.terminal.detect.TERMINAL_OVERRIDE", None)

        from flaude.terminal.detect import detect_terminal

        assert detect_terminal() == "IntelliJ"

    def test_unknown_terminal(self, monkeypatch):
        mock_result = MagicMock()
        mock_result.stdout = "Finder, Dock, Safari\n"
        monkeypatch.setattr(
            "flaude.terminal.detect.subprocess.run", lambda *a, **kw: mock_result
        )
        monkeypatch.setattr("flaude.terminal.detect.TERMINAL_OVERRIDE", None)

        from flaude.terminal.detect import detect_terminal

        assert detect_terminal() is None

    def test_subprocess_failure_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "flaude.terminal.detect.subprocess.run",
            lambda *a, **kw: (_ for _ in ()).throw(
                subprocess.TimeoutExpired("osascript", 5)
            ),
        )
        monkeypatch.setattr("flaude.terminal.detect.TERMINAL_OVERRIDE", None)

        from flaude.terminal.detect import detect_terminal

        assert detect_terminal() is None


# ---------------------------------------------------------------------------
# launch.py — AppleScript generation
# ---------------------------------------------------------------------------


class TestBuildLaunchScript:
    """_build_launch_script produces correct AppleScript for each terminal."""

    def test_iterm2_script(self):
        from flaude.terminal.launch import _build_launch_script

        script = _build_launch_script("iTerm2", "/tmp/proj")
        assert script is not None
        assert "iTerm2" in script
        assert "create tab" in script
        assert "cd /tmp/proj && claude" in script

    def test_terminal_script(self):
        from flaude.terminal.launch import _build_launch_script

        script = _build_launch_script("Terminal", "/tmp/proj")
        assert script is not None
        assert 'tell application "Terminal"' in script
        assert "cd /tmp/proj && claude" in script

    def test_ghostty_script(self):
        from flaude.terminal.launch import _build_launch_script

        script = _build_launch_script("Ghostty", "/tmp/proj")
        assert script is not None
        assert "Ghostty" in script

    def test_intellij_returns_none(self):
        from flaude.terminal.launch import _build_launch_script

        assert _build_launch_script("IntelliJ", "/tmp/proj") is None

    def test_unknown_terminal_uses_generic_fallback(self):
        from flaude.terminal.launch import _build_launch_script

        script = _build_launch_script("RandomTerminal", "/tmp/proj")
        assert script is not None
        assert "RandomTerminal" in script
        assert "pbcopy" in script

    def test_cwd_with_quotes_escaped(self):
        from flaude.terminal.launch import _build_launch_script

        script = _build_launch_script("iTerm2", '/tmp/my "project"')
        assert script is not None
        assert '\\"project\\"' in script


class TestLaunchSession:
    def test_success(self, monkeypatch):
        from flaude.terminal.launch import launch_session

        mock_result = MagicMock()
        mock_result.returncode = 0
        monkeypatch.setattr(
            "flaude.terminal.launch.subprocess.run", lambda *a, **kw: mock_result
        )
        assert launch_session("iTerm2", "/tmp/proj") is True

    def test_failure(self, monkeypatch):
        from flaude.terminal.launch import launch_session

        mock_result = MagicMock()
        mock_result.returncode = 1
        monkeypatch.setattr(
            "flaude.terminal.launch.subprocess.run", lambda *a, **kw: mock_result
        )
        assert launch_session("iTerm2", "/tmp/proj") is False

    def test_no_terminal(self):
        from flaude.terminal.launch import launch_session

        assert launch_session(None, "/tmp/proj") is False

    def test_no_cwd(self):
        from flaude.terminal.launch import launch_session

        assert launch_session("iTerm2", "") is False


# ---------------------------------------------------------------------------
# inject.py — text injection via AppleScript
# ---------------------------------------------------------------------------


class TestSendTextToSession:
    def test_success(self, monkeypatch):
        from flaude.terminal.inject import send_text_to_session

        mock_result = MagicMock()
        mock_result.stdout = "sent"
        monkeypatch.setattr(
            "flaude.terminal.inject.subprocess.run", lambda *a, **kw: mock_result
        )
        assert send_text_to_session("/dev/ttys006", "hello") is True

    def test_not_found(self, monkeypatch):
        from flaude.terminal.inject import send_text_to_session

        mock_result = MagicMock()
        mock_result.stdout = "not_found"
        monkeypatch.setattr(
            "flaude.terminal.inject.subprocess.run", lambda *a, **kw: mock_result
        )
        assert send_text_to_session("/dev/ttys006", "hello") is False

    def test_double_quotes_escaped(self, monkeypatch):
        from flaude.terminal.inject import send_text_to_session

        captured = []

        def capture_run(cmd, **kw):
            captured.append(cmd)
            result = MagicMock()
            result.stdout = "sent"
            return result

        monkeypatch.setattr("flaude.terminal.inject.subprocess.run", capture_run)
        send_text_to_session("/dev/ttys006", 'say "hello"')
        assert '\\"hello\\"' in captured[0][2]

    def test_subprocess_failure_returns_false(self, monkeypatch):
        from flaude.terminal.inject import send_text_to_session

        monkeypatch.setattr(
            "flaude.terminal.inject.subprocess.run",
            lambda *a, **kw: (_ for _ in ()).throw(
                subprocess.TimeoutExpired("osascript", 5)
            ),
        )
        assert send_text_to_session("/dev/ttys006", "hello") is False
