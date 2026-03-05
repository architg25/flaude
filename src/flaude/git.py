"""Git metadata extraction for session enrichment."""

from __future__ import annotations

import subprocess
from pathlib import Path


def get_git_info(cwd: str) -> tuple[str | None, str | None, bool]:
    """Return (repo_root, branch, is_worktree) for a directory.

    Uses a single ``git rev-parse`` call. Returns (None, None, False)
    if *cwd* is not inside a git repo or on any error.
    """
    if not cwd:
        return None, None, False
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                cwd,
                "rev-parse",
                "--show-toplevel",
                "--git-common-dir",
                "--abbrev-ref",
                "HEAD",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return None, None, False
    except (subprocess.TimeoutExpired, OSError):
        return None, None, False

    lines = result.stdout.strip().splitlines()
    if len(lines) < 3:
        return None, None, False

    toplevel = lines[0]
    git_common_dir = lines[1]
    branch = lines[2]

    # Resolve git_common_dir to absolute path
    common_abs = Path(git_common_dir)
    if not common_abs.is_absolute():
        common_abs = (Path(toplevel) / git_common_dir).resolve()

    # Canonical repo root = parent of the shared .git directory
    repo_root = str(common_abs.parent)
    is_worktree = repo_root != toplevel

    if branch == "HEAD":
        branch = None

    return repo_root, branch, is_worktree
