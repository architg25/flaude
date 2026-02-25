"""Tests for TTY-based terminal navigation.

The core problem: when multiple sessions share the same cwd, navigation
by cwd always jumps to the first matching tab. TTY matching solves this
because each terminal tab has a unique TTY device (e.g. /dev/ttys006).
"""

from unittest.mock import MagicMock, patch

import pytest

from helpers import make_state
from flaude.hooks.dispatcher import (
    _detect_tty,
    _handle_session_start,
    _load_or_create,
)
from flaude.terminal.navigate import (
    _cwds_match,
    _navigate_iterm2,
    navigate_to_session,
)


# ---------------------------------------------------------------------------
# _detect_tty — PPID-based TTY detection
# ---------------------------------------------------------------------------


class TestDetectTty:
    """TTY detection walks up the process tree via ps."""

    def test_finds_tty_on_parent(self):
        """When parent has a real TTY, return /dev/<tty>."""
        mock_result = MagicMock()
        mock_result.stdout = "ttys006  1234\n"
        with patch("subprocess.run", return_value=mock_result):
            tty = _detect_tty()
        assert tty == "/dev/ttys006"

    def test_skips_no_tty_parent_walks_up(self):
        """When parent has ??, walk to grandparent."""
        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.stdout = "??  555\n"  # parent: no tty, ppid=555
            else:
                result.stdout = "ttys003  1\n"  # grandparent: has tty
            return result

        with patch("subprocess.run", side_effect=fake_run):
            tty = _detect_tty()
        assert tty == "/dev/ttys003"
        assert call_count == 2

    def test_returns_none_when_no_tty_found(self):
        """When entire chain has ??, return None."""
        mock_result = MagicMock()
        mock_result.stdout = "??  1\n"  # ppid=1 (init), loop stops
        with patch("subprocess.run", return_value=mock_result):
            tty = _detect_tty()
        assert tty is None

    def test_returns_none_on_empty_output(self):
        """When ps returns nothing, return None."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            tty = _detect_tty()
        assert tty is None

    def test_returns_none_on_subprocess_error(self):
        """When ps fails, return None gracefully."""
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ps", 3)):
            tty = _detect_tty()
        assert tty is None

    def test_max_five_hops(self):
        """Walk stops after 5 levels to prevent infinite loops."""
        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            # Always return ??, never a real TTY, with a valid ppid
            result.stdout = f"??  {1000 + call_count}\n"
            return result

        with patch("subprocess.run", side_effect=fake_run):
            tty = _detect_tty()
        assert tty is None
        assert call_count == 5


# ---------------------------------------------------------------------------
# TTY stored in session state via hooks
# ---------------------------------------------------------------------------


class TestTtyInSessionState:
    """Verify TTY is stored and backfilled in session state."""

    def test_session_start_stores_tty(self, mgr):
        with patch("flaude.hooks.dispatcher._detect_tty", return_value="/dev/ttys006"):
            _handle_session_start(
                {
                    "session_id": "tty-1",
                    "cwd": "/tmp/proj",
                    "permission_mode": "default",
                },
                mgr,
            )
        state = mgr.load_session("tty-1")
        assert state.tty == "/dev/ttys006"

    def test_session_start_stores_none_when_no_tty(self, mgr):
        with patch("flaude.hooks.dispatcher._detect_tty", return_value=None):
            _handle_session_start(
                {"session_id": "tty-2", "cwd": "/tmp", "permission_mode": "default"},
                mgr,
            )
        state = mgr.load_session("tty-2")
        assert state.tty is None

    def test_load_or_create_backfills_tty(self, mgr):
        """Existing session without tty gets it backfilled."""
        existing = make_state("tty-3", tty=None)
        mgr.save_session(existing)

        with patch("flaude.hooks.dispatcher._detect_tty", return_value="/dev/ttys009"):
            state = _load_or_create({"session_id": "tty-3", "cwd": "/tmp"}, mgr)
        assert state.tty == "/dev/ttys009"

    def test_load_or_create_preserves_existing_tty(self, mgr):
        """Existing session with tty doesn't get overwritten."""
        existing = make_state("tty-4", tty="/dev/ttys001")
        mgr.save_session(existing)

        with patch("flaude.hooks.dispatcher._detect_tty", return_value="/dev/ttys999"):
            state = _load_or_create({"session_id": "tty-4", "cwd": "/tmp"}, mgr)
        assert state.tty == "/dev/ttys001"

    def test_tty_survives_json_roundtrip(self, mgr):
        """TTY persists through save → load cycle."""
        state = make_state("tty-5", tty="/dev/ttys006")
        mgr.save_session(state)
        loaded = mgr.load_session("tty-5")
        assert loaded.tty == "/dev/ttys006"


# ---------------------------------------------------------------------------
# iTerm2 navigation — TTY matching fast path
# ---------------------------------------------------------------------------

# Simulated AppleScript output: 3 tabs, two share the same cwd
ITERM_TTY_OUTPUT = "/dev/ttys000|1|1\n" "/dev/ttys001|1|2\n" "/dev/ttys002|1|3\n"


def _mock_osascript(list_output):
    """Create a mock for subprocess.run that returns list_output for the
    first call (AppleScript list) and succeeds for the second (select)."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        result = MagicMock()
        result.returncode = 0
        if len(calls) == 1:
            result.stdout = list_output
        else:
            result.stdout = ""
        return result

    return fake_run, calls


class TestIterm2TtyMatching:
    """iTerm2 navigation should prefer TTY matching over cwd matching."""

    def test_tty_match_selects_correct_tab(self):
        """When tty is provided, match directly without cwd resolution."""
        fake_run, calls = _mock_osascript(ITERM_TTY_OUTPUT)
        with patch("flaude.terminal.navigate.subprocess.run", side_effect=fake_run):
            result = _navigate_iterm2("/some/cwd", tty="/dev/ttys001")
        assert result is True
        # Second call is the select script — verify it targets tab 2
        select_script = calls[1][2]  # ["osascript", "-e", <script>]
        assert "tab 2" in select_script
        assert "window 1" in select_script

    def test_tty_match_third_tab(self):
        fake_run, calls = _mock_osascript(ITERM_TTY_OUTPUT)
        with patch("flaude.terminal.navigate.subprocess.run", side_effect=fake_run):
            result = _navigate_iterm2("/any/cwd", tty="/dev/ttys002")
        assert result is True
        select_script = calls[1][2]
        assert "tab 3" in select_script

    def test_tty_not_found_falls_back_to_cwd(self):
        """When tty doesn't match any tab, fall back to cwd matching."""
        fake_run, calls = _mock_osascript(ITERM_TTY_OUTPUT)
        with (
            patch("flaude.terminal.navigate.subprocess.run", side_effect=fake_run),
            patch(
                "flaude.terminal.navigate._get_cwd_for_tty",
                side_effect=lambda t: {
                    "/dev/ttys000": "/proj/a",
                    "/dev/ttys001": "/proj/b",
                    "/dev/ttys002": "/proj/c",
                }.get(t),
            ),
        ):
            result = _navigate_iterm2("/proj/b", tty="/dev/ttys999")
        assert result is True
        select_script = calls[1][2]
        assert "tab 2" in select_script  # matched by cwd, not tty

    def test_no_tty_uses_cwd_matching(self):
        """When tty is None, use cwd matching."""
        fake_run, calls = _mock_osascript(ITERM_TTY_OUTPUT)
        with (
            patch("flaude.terminal.navigate.subprocess.run", side_effect=fake_run),
            patch(
                "flaude.terminal.navigate._get_cwd_for_tty",
                side_effect=lambda t: {
                    "/dev/ttys000": "/proj/a",
                    "/dev/ttys001": "/proj/target",
                    "/dev/ttys002": "/proj/c",
                }.get(t),
            ),
        ):
            result = _navigate_iterm2("/proj/target", tty=None)
        assert result is True
        select_script = calls[1][2]
        assert "tab 2" in select_script

    def test_same_cwd_different_tty_goes_to_correct_tab(self):
        """The original bug: two sessions in same dir, TTY distinguishes them."""
        fake_run, calls = _mock_osascript(ITERM_TTY_OUTPUT)
        with patch("flaude.terminal.navigate.subprocess.run", side_effect=fake_run):
            # Session on ttys002, even though all tabs have same cwd
            result = _navigate_iterm2("/same/project", tty="/dev/ttys002")
        assert result is True
        select_script = calls[1][2]
        assert "tab 3" in select_script  # NOT tab 1

    def test_no_match_returns_false(self):
        """When neither tty nor cwd matches, return False."""
        fake_run, _ = _mock_osascript(ITERM_TTY_OUTPUT)
        with (
            patch("flaude.terminal.navigate.subprocess.run", side_effect=fake_run),
            patch("flaude.terminal.navigate._get_cwd_for_tty", return_value=None),
        ):
            result = _navigate_iterm2("/no/match", tty="/dev/ttys999")
        assert result is False

    def test_empty_applescript_output_returns_false(self):
        """When iTerm2 returns no sessions."""
        fake_run, _ = _mock_osascript("")
        with patch("flaude.terminal.navigate.subprocess.run", side_effect=fake_run):
            result = _navigate_iterm2("/any", tty="/dev/ttys000")
        assert result is False


# ---------------------------------------------------------------------------
# navigate_to_session top-level wiring
# ---------------------------------------------------------------------------


class TestNavigateToSession:
    def test_passes_tty_to_iterm2(self):
        with patch(
            "flaude.terminal.navigate._navigate_iterm2", return_value=True
        ) as mock:
            navigate_to_session("iTerm2", "/tmp/proj", tty="/dev/ttys006")
        mock.assert_called_once_with("/tmp/proj", tty="/dev/ttys006")

    def test_tty_ignored_for_non_iterm(self):
        """Non-iTerm terminals don't use TTY matching."""
        with patch("flaude.terminal.navigate.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="true", returncode=0)
            navigate_to_session("Warp", "/tmp/proj", tty="/dev/ttys006")
        # Warp script doesn't reference tty at all
        script = mock_run.call_args[0][0][2]
        assert "ttys006" not in script


# ---------------------------------------------------------------------------
# _cwds_match edge cases
# ---------------------------------------------------------------------------


class TestCwdsMatch:
    def test_exact_match(self):
        assert _cwds_match("/Users/me/proj", "/Users/me/proj") is True

    def test_trailing_slash(self):
        assert _cwds_match("/Users/me/proj/", "/Users/me/proj") is True
        assert _cwds_match("/Users/me/proj", "/Users/me/proj/") is True

    def test_different_paths(self):
        assert _cwds_match("/Users/me/proj-a", "/Users/me/proj-b") is False

    def test_parent_does_not_match_child(self):
        """Exact match only — parent dirs should NOT match."""
        assert _cwds_match("/Users/me", "/Users/me/proj") is False
