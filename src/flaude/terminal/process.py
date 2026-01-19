"""Find and kill Claude Code processes."""

import subprocess


def kill_session(session_id: str) -> bool:
    """Kill a Claude Code session by matching its session ID in the process args.

    Sends SIGTERM via pkill for a graceful shutdown. Returns True if a process was found.
    """
    try:
        result = subprocess.run(
            ["pkill", "-f", f"claude.*{session_id}"],
            capture_output=True,
            timeout=5,
        )
        # pkill returns 0 if at least one process matched
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
