"""tmux backend for session management — navigate, launch, inject, query."""

import os
import shlex
import shutil
import subprocess

from flaude.constants import TMUX_SESSION_NAME
from flaude.terminal.detect import _TERM_PROGRAM_MAP


def is_tmux_available() -> bool:
    """Check if tmux is installed."""
    return shutil.which("tmux") is not None


def is_flaude_in_tmux() -> bool:
    """Check if flaude itself is running inside a tmux session."""
    return bool(os.environ.get("TMUX"))


def get_flaude_tmux_session() -> str | None:
    """Get the tmux session name flaude is running in, if any."""
    if not os.environ.get("TMUX"):
        return None
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#{session_name}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _flaude_session_exists() -> bool:
    """Check if the flaude tmux session exists."""
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", TMUX_SESSION_NAME],
            capture_output=True,
            timeout=3,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _get_tmux_session_for_pane(pane_id: str) -> str | None:
    """Get the tmux session name that owns a pane."""
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-t", pane_id, "-p", "#{session_name}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def launch_tmux_session(cwd: str) -> bool:
    """Launch a new Claude session in a tmux window.

    Creates the flaude tmux session if it doesn't exist, otherwise
    adds a new window to it. Returns True on success.
    """
    if not is_tmux_available():
        return False

    cwd = os.path.expanduser(cwd)
    window_name = os.path.basename(cwd) or "claude"
    quoted_cwd = shlex.quote(cwd)
    cmd = f"cd {quoted_cwd} && claude"

    try:
        if not _flaude_session_exists():
            result = subprocess.run(
                [
                    "tmux",
                    "new-session",
                    "-d",
                    "-s",
                    TMUX_SESSION_NAME,
                    "-n",
                    window_name,
                    cmd,
                ],
                capture_output=True,
                timeout=5,
            )
        else:
            result = subprocess.run(
                [
                    "tmux",
                    "new-window",
                    "-t",
                    TMUX_SESSION_NAME,
                    "-n",
                    window_name,
                    cmd,
                ],
                capture_output=True,
                timeout=5,
            )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def navigate_tmux_session(tmux_pane: str) -> bool:
    """Select a tmux pane by its ID (e.g., '%5').

    Used when flaude is already inside the same tmux server.
    Switches to the window containing this pane.
    """
    session_name = _get_tmux_session_for_pane(tmux_pane)
    if not session_name:
        return False
    try:
        result = subprocess.run(
            ["tmux", "select-window", "-t", tmux_pane],
            capture_output=True,
            timeout=3,
        )
        if result.returncode != 0:
            return False
        # Also select the specific pane if it's a split
        subprocess.run(
            ["tmux", "select-pane", "-t", tmux_pane],
            capture_output=True,
            timeout=3,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def build_tmux_attach_command(tmux_pane: str) -> list[str]:
    """Build a command list to attach to the tmux session containing a pane."""
    session_name = _get_tmux_session_for_pane(tmux_pane)
    target = session_name or TMUX_SESSION_NAME
    return ["tmux", "attach-session", "-t", target, ";", "select-pane", "-t", tmux_pane]


def build_tmux_attach_shell_command(tmux_pane: str) -> str:
    """Build a shell command string for AppleScript terminal launch."""
    session_name = _get_tmux_session_for_pane(tmux_pane)
    target = session_name or TMUX_SESSION_NAME
    return f"tmux attach-session -t {shlex.quote(target)} \\; select-pane -t {shlex.quote(tmux_pane)}"


def send_text_tmux(tmux_pane: str, text: str) -> bool:
    """Send text to a tmux pane via send-keys.

    Works for any terminal. Equivalent to typing the text and pressing Enter.
    """
    if not tmux_pane or not text:
        return False
    try:
        result = subprocess.run(
            ["tmux", "send-keys", "-t", tmux_pane, text, "Enter"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def get_tmux_client_tty(tmux_pane: str) -> str | None:
    """Get the TTY of the terminal client attached to a pane's tmux session.

    Used for iTerm2 tab reuse — if we know which TTY the tmux client is on,
    we can find the iTerm2 tab via existing TTY matching.
    """
    session_name = _get_tmux_session_for_pane(tmux_pane)
    if not session_name:
        return None
    try:
        result = subprocess.run(
            [
                "tmux",
                "list-clients",
                "-t",
                session_name,
                "-F",
                "#{client_tty}",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Return first attached client's TTY
            return result.stdout.strip().splitlines()[0]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def get_tmux_prefix() -> str:
    """Get the tmux prefix key for display (e.g., 'Ctrl+B')."""
    try:
        result = subprocess.run(
            ["tmux", "show-options", "-g", "prefix"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Output: "prefix C-b" or "prefix C-a"
            parts = result.stdout.strip().split()
            if len(parts) >= 2:
                key = parts[1]
                if key.startswith("C-"):
                    return f"Ctrl+{key[2:].upper()}"
                return key
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return "Ctrl+B"


def detect_tmux_info() -> tuple[bool, str | None, str | None]:
    """Detect tmux environment from within a hook.

    Returns (is_tmux, pane_id, parent_terminal).
    Called by the hook dispatcher during SessionStart.
    """
    tmux_env = os.environ.get("TMUX")
    if not tmux_env:
        return False, None, None

    pane_id = os.environ.get("TMUX_PANE")

    # Detect parent terminal: the terminal that started the tmux server.
    # tmux preserves the environment from when it was created.
    parent_terminal = _detect_parent_terminal_of_tmux()

    return True, pane_id, parent_terminal


_TERMINAL_PROCESS_NAMES = {
    "iTerm2": "iTerm",
    "Ghostty": "ghostty",
    "Terminal": "Terminal.app",
    "Warp": "Warp",
}


def _detect_parent_terminal_of_tmux() -> str | None:
    """Detect the terminal wrapping tmux.

    1. tmux show-environment TERM_PROGRAM (fast, if the terminal set it)
    2. Walk the tmux client's parent process tree for a known terminal
    """
    # Strategy 1: tmux environment
    try:
        result = subprocess.run(
            ["tmux", "show-environment", "TERM_PROGRAM"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        line = result.stdout.strip()
        if "=" in line and not line.startswith("-"):
            value = line.split("=", 1)[1]
            terminal = _TERM_PROGRAM_MAP.get(value)
            if terminal:
                return terminal
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Strategy 2: walk the tmux client's parent process tree
    try:
        result = subprocess.run(
            ["tmux", "list-clients", "-F", "#{client_pid}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            client_pid = int(result.stdout.strip().splitlines()[0])
            terminal = _find_terminal_in_ancestors(client_pid)
            if terminal:
                return terminal
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
        pass

    return None


def _find_terminal_in_ancestors(pid: int) -> str | None:
    """Walk the process tree from pid upwards looking for a known terminal."""
    for _ in range(10):
        if pid <= 1:
            break
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "ppid=,comm="],
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            break
        line = result.stdout.strip()
        if not line:
            break
        parts = line.split(None, 1)
        if len(parts) < 2:
            break
        ppid_str, comm = parts
        for terminal_name, needle in _TERMINAL_PROCESS_NAMES.items():
            if needle in comm:
                return terminal_name
        if "jetbrains" in comm.lower() or "idea" in comm.lower():
            return "IntelliJ"
        try:
            pid = int(ppid_str)
        except ValueError:
            break
    return None


def list_tmux_panes() -> list[tuple[int, str]]:
    """List all tmux panes with their PIDs and pane IDs.

    Returns list of (pane_pid, pane_id) tuples.
    Used for session discovery at startup.
    """
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{pane_pid} #{pane_id}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode != 0:
            return []
        panes = []
        for line in result.stdout.strip().splitlines():
            parts = line.strip().split()
            if len(parts) == 2:
                try:
                    panes.append((int(parts[0]), parts[1]))
                except ValueError:
                    continue
        return panes
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []
