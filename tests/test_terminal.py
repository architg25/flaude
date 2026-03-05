"""Tests for terminal detection, launch, and text injection modules."""

import subprocess
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# detect.py — terminal detection
# ---------------------------------------------------------------------------


class TestDetectTerminal:
    """Tests for detect_terminal()."""

    def test_override_env_var(self, monkeypatch):
        """FLAUDE_TERMINAL env var bypasses all detection."""
        monkeypatch.setenv("FLAUDE_TERMINAL", "WezTerm")
        # Re-import to pick up the new env var value in constants
        import importlib
        import flaude.constants

        importlib.reload(flaude.constants)
        import flaude.terminal.detect

        importlib.reload(flaude.terminal.detect)
        from flaude.terminal.detect import detect_terminal

        assert detect_terminal() == "WezTerm"

        # Clean up: unset and reload so other tests aren't affected
        monkeypatch.delenv("FLAUDE_TERMINAL", raising=False)
        importlib.reload(flaude.constants)
        importlib.reload(flaude.terminal.detect)

    def test_known_terminal_iterm2(self, monkeypatch):
        """Detects iTerm2 from process list."""
        mock_result = MagicMock()
        mock_result.stdout = "Finder, Dock, iTerm2, Spotlight\n"
        monkeypatch.setattr(
            "flaude.terminal.detect.subprocess.run", lambda *a, **kw: mock_result
        )
        monkeypatch.setattr("flaude.terminal.detect.TERMINAL_OVERRIDE", None)

        from flaude.terminal.detect import detect_terminal

        assert detect_terminal() == "iTerm2"

    def test_known_terminal_ghostty(self, monkeypatch):
        """Detects Ghostty from process list."""
        mock_result = MagicMock()
        mock_result.stdout = "Finder, Ghostty, Dock\n"
        monkeypatch.setattr(
            "flaude.terminal.detect.subprocess.run", lambda *a, **kw: mock_result
        )
        monkeypatch.setattr("flaude.terminal.detect.TERMINAL_OVERRIDE", None)

        from flaude.terminal.detect import detect_terminal

        assert detect_terminal() == "Ghostty"

    def test_known_terminal_preference_order(self, monkeypatch):
        """When multiple terminals are running, first in list wins."""
        mock_result = MagicMock()
        mock_result.stdout = "Ghostty, iTerm2, Terminal\n"
        monkeypatch.setattr(
            "flaude.terminal.detect.subprocess.run", lambda *a, **kw: mock_result
        )
        monkeypatch.setattr("flaude.terminal.detect.TERMINAL_OVERRIDE", None)

        from flaude.terminal.detect import detect_terminal

        # iTerm2 comes before Ghostty in KNOWN_TERMINALS
        assert detect_terminal() == "iTerm2"

    def test_jetbrains_ide_detected(self, monkeypatch):
        """JetBrains IDEs return 'IntelliJ'."""
        mock_result = MagicMock()
        mock_result.stdout = "Finder, Dock, PyCharm\n"
        monkeypatch.setattr(
            "flaude.terminal.detect.subprocess.run", lambda *a, **kw: mock_result
        )
        monkeypatch.setattr("flaude.terminal.detect.TERMINAL_OVERRIDE", None)

        from flaude.terminal.detect import detect_terminal

        assert detect_terminal() == "IntelliJ"

    def test_jetbrains_idea(self, monkeypatch):
        """JetBrains 'idea' process name also detected."""
        mock_result = MagicMock()
        mock_result.stdout = "Finder, idea, Dock\n"
        monkeypatch.setattr(
            "flaude.terminal.detect.subprocess.run", lambda *a, **kw: mock_result
        )
        monkeypatch.setattr("flaude.terminal.detect.TERMINAL_OVERRIDE", None)

        from flaude.terminal.detect import detect_terminal

        assert detect_terminal() == "IntelliJ"

    def test_unknown_terminal(self, monkeypatch):
        """Returns None when no recognized terminal is found."""
        mock_result = MagicMock()
        mock_result.stdout = "Finder, Dock, Safari\n"
        monkeypatch.setattr(
            "flaude.terminal.detect.subprocess.run", lambda *a, **kw: mock_result
        )
        monkeypatch.setattr("flaude.terminal.detect.TERMINAL_OVERRIDE", None)

        from flaude.terminal.detect import detect_terminal

        assert detect_terminal() is None

    def test_subprocess_timeout(self, monkeypatch):
        """Returns None when osascript times out."""

        def raise_timeout(*a, **kw):
            raise subprocess.TimeoutExpired("osascript", 5)

        monkeypatch.setattr("flaude.terminal.detect.subprocess.run", raise_timeout)
        monkeypatch.setattr("flaude.terminal.detect.TERMINAL_OVERRIDE", None)

        from flaude.terminal.detect import detect_terminal

        assert detect_terminal() is None

    def test_subprocess_file_not_found(self, monkeypatch):
        """Returns None when osascript binary not found."""

        def raise_fnf(*a, **kw):
            raise FileNotFoundError("osascript")

        monkeypatch.setattr("flaude.terminal.detect.subprocess.run", raise_fnf)
        monkeypatch.setattr("flaude.terminal.detect.TERMINAL_OVERRIDE", None)

        from flaude.terminal.detect import detect_terminal

        assert detect_terminal() is None


# ---------------------------------------------------------------------------
# launch.py — session launching
# ---------------------------------------------------------------------------


class TestBuildLaunchScript:
    """Tests for _build_launch_script()."""

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
        assert "do script" in script
        assert "cd /tmp/proj && claude" in script

    def test_ghostty_script(self):
        from flaude.terminal.launch import _build_launch_script

        script = _build_launch_script("Ghostty", "/tmp/proj")
        assert script is not None
        assert "Ghostty" in script
        assert "keystroke" in script

    def test_warp_script(self):
        from flaude.terminal.launch import _build_launch_script

        script = _build_launch_script("Warp", "/tmp/proj")
        assert script is not None
        assert "Warp" in script
        assert 'keystroke "t" using command down' in script

    def test_intellij_returns_none(self):
        """IntelliJ can't launch terminal tabs programmatically."""
        from flaude.terminal.launch import _build_launch_script

        assert _build_launch_script("IntelliJ", "/tmp/proj") is None

    def test_unknown_terminal_returns_none(self):
        from flaude.terminal.launch import _build_launch_script

        assert _build_launch_script("SomeRandomTerminal", "/tmp/proj") is None

    def test_cwd_with_spaces_escaped(self):
        """Paths with special chars are escaped in the script."""
        from flaude.terminal.launch import _build_launch_script

        script = _build_launch_script("iTerm2", '/tmp/my "project"')
        assert script is not None
        # Double quotes in path should be escaped
        assert '\\"project\\"' in script


class TestLaunchSession:
    """Tests for launch_session()."""

    def test_success(self, monkeypatch):
        from flaude.terminal.launch import launch_session

        mock_result = MagicMock()
        mock_result.returncode = 0
        monkeypatch.setattr(
            "flaude.terminal.launch.subprocess.run", lambda *a, **kw: mock_result
        )
        assert launch_session("iTerm2", "/tmp/proj") is True

    def test_failure_returncode(self, monkeypatch):
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

    def test_unknown_terminal_returns_false(self, monkeypatch):
        """Unknown terminal produces no script, so launch returns False."""
        from flaude.terminal.launch import launch_session

        # subprocess.run should never be called
        monkeypatch.setattr(
            "flaude.terminal.launch.subprocess.run",
            lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not call")),
        )
        assert launch_session("UnknownTerminal", "/tmp/proj") is False

    def test_subprocess_timeout(self, monkeypatch):
        from flaude.terminal.launch import launch_session

        def raise_timeout(*a, **kw):
            raise subprocess.TimeoutExpired("osascript", 5)

        monkeypatch.setattr("flaude.terminal.launch.subprocess.run", raise_timeout)
        assert launch_session("iTerm2", "/tmp/proj") is False

    def test_subprocess_oserror(self, monkeypatch):
        from flaude.terminal.launch import launch_session

        def raise_oserror(*a, **kw):
            raise OSError("something broke")

        monkeypatch.setattr("flaude.terminal.launch.subprocess.run", raise_oserror)
        assert launch_session("iTerm2", "/tmp/proj") is False


# ---------------------------------------------------------------------------
# inject.py — text injection into terminal sessions
# ---------------------------------------------------------------------------


class TestSendTextToSession:
    """Tests for send_text_to_session()."""

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

    def test_empty_tty_returns_false(self):
        from flaude.terminal.inject import send_text_to_session

        assert send_text_to_session("", "hello") is False

    def test_empty_text_returns_false(self):
        from flaude.terminal.inject import send_text_to_session

        assert send_text_to_session("/dev/ttys006", "") is False

    def test_none_tty_returns_false(self):
        from flaude.terminal.inject import send_text_to_session

        assert send_text_to_session(None, "hello") is False

    def test_none_text_returns_false(self):
        from flaude.terminal.inject import send_text_to_session

        assert send_text_to_session("/dev/ttys006", None) is False

    def test_special_chars_double_quotes(self, monkeypatch):
        """Double quotes in text are escaped for AppleScript."""
        from flaude.terminal.inject import send_text_to_session

        captured_scripts = []

        def capture_run(cmd, **kw):
            captured_scripts.append(cmd)
            result = MagicMock()
            result.stdout = "sent"
            return result

        monkeypatch.setattr("flaude.terminal.inject.subprocess.run", capture_run)
        send_text_to_session("/dev/ttys006", 'say "hello"')

        script = captured_scripts[0][2]  # ["osascript", "-e", <script>]
        # The quotes should be escaped as \"
        assert '\\"hello\\"' in script

    def test_special_chars_backslashes(self, monkeypatch):
        """Backslashes in text are escaped for AppleScript."""
        from flaude.terminal.inject import send_text_to_session

        captured_scripts = []

        def capture_run(cmd, **kw):
            captured_scripts.append(cmd)
            result = MagicMock()
            result.stdout = "sent"
            return result

        monkeypatch.setattr("flaude.terminal.inject.subprocess.run", capture_run)
        send_text_to_session("/dev/ttys006", "path\\to\\file")

        script = captured_scripts[0][2]
        # Each \ should become \\
        assert "path\\\\to\\\\file" in script

    def test_newlines_converted_to_linefeed(self, monkeypatch):
        """Newlines in text become AppleScript linefeed concatenation."""
        from flaude.terminal.inject import send_text_to_session

        captured_scripts = []

        def capture_run(cmd, **kw):
            captured_scripts.append(cmd)
            result = MagicMock()
            result.stdout = "sent"
            return result

        monkeypatch.setattr("flaude.terminal.inject.subprocess.run", capture_run)
        send_text_to_session("/dev/ttys006", "line1\nline2")

        script = captured_scripts[0][2]
        assert "linefeed" in script

    def test_subprocess_timeout_returns_false(self, monkeypatch):
        from flaude.terminal.inject import send_text_to_session

        def raise_timeout(*a, **kw):
            raise subprocess.TimeoutExpired("osascript", 5)

        monkeypatch.setattr("flaude.terminal.inject.subprocess.run", raise_timeout)
        assert send_text_to_session("/dev/ttys006", "hello") is False

    def test_subprocess_file_not_found_returns_false(self, monkeypatch):
        from flaude.terminal.inject import send_text_to_session

        def raise_fnf(*a, **kw):
            raise FileNotFoundError("osascript")

        monkeypatch.setattr("flaude.terminal.inject.subprocess.run", raise_fnf)
        assert send_text_to_session("/dev/ttys006", "hello") is False

    def test_subprocess_oserror_returns_false(self, monkeypatch):
        from flaude.terminal.inject import send_text_to_session

        def raise_oserror(*a, **kw):
            raise OSError("broken")

        monkeypatch.setattr("flaude.terminal.inject.subprocess.run", raise_oserror)
        assert send_text_to_session("/dev/ttys006", "hello") is False

    def test_tty_in_script(self, monkeypatch):
        """The tty device path appears in the generated AppleScript."""
        from flaude.terminal.inject import send_text_to_session

        captured_scripts = []

        def capture_run(cmd, **kw):
            captured_scripts.append(cmd)
            result = MagicMock()
            result.stdout = "sent"
            return result

        monkeypatch.setattr("flaude.terminal.inject.subprocess.run", capture_run)
        send_text_to_session("/dev/ttys042", "test")

        script = captured_scripts[0][2]
        assert "/dev/ttys042" in script
