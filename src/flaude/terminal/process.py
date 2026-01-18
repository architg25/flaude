"""Find and kill Claude Code processes."""

import os
import signal
import subprocess


def find_claude_pid_for_cwd(cwd: str) -> int | None:
    """Find a claude process whose working directory matches cwd."""
    try:
        # Get all claude processes with their PIDs and cwds
        result = subprocess.run(
            ["lsof", "-d", "cwd", "-c", "claude", "-c", "node", "-Fp", "-Fn"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        # Parse lsof output: lines alternate between p<pid> and n<path>
        current_pid = None
        cwd_normalized = cwd.rstrip("/")
        for line in result.stdout.strip().splitlines():
            if line.startswith("p"):
                current_pid = int(line[1:])
            elif line.startswith("n") and current_pid is not None:
                process_cwd = line[1:].rstrip("/")
                if process_cwd == cwd_normalized:
                    return current_pid
                current_pid = None

        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, OSError):
        return None


def kill_session(cwd: str) -> bool:
    """Kill a Claude Code session by finding its process via cwd.

    Sends SIGTERM for a graceful shutdown. Returns True if killed.
    """
    pid = find_claude_pid_for_cwd(cwd)
    if pid is None:
        return False

    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except (ProcessLookupError, PermissionError):
        return False
