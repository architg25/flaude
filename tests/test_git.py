"""Tests for flaude.git module."""

from unittest.mock import patch, MagicMock
import subprocess

from flaude.git import get_git_info


def _mock_run(toplevel: str, common_dir: str, branch: str, returncode: int = 0):
    """Create a mock for subprocess.run returning git rev-parse output."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = f"{toplevel}\n{common_dir}\n{branch}\n"
    return result


class TestGetGitInfo:
    def test_empty_cwd(self):
        assert get_git_info("") == (None, None, False)

    @patch("flaude.git.subprocess.run")
    def test_not_a_git_repo(self, mock_run):
        mock_run.return_value = _mock_run("", "", "", returncode=128)
        assert get_git_info("/tmp/not-a-repo") == (None, None, False)

    @patch("flaude.git.subprocess.run")
    def test_main_checkout(self, mock_run):
        mock_run.return_value = _mock_run("/Users/me/myrepo", ".git", "main")
        repo_root, branch, is_wt = get_git_info("/Users/me/myrepo/src")
        assert repo_root == "/Users/me/myrepo"
        assert branch == "main"
        assert is_wt is False

    @patch("flaude.git.subprocess.run")
    def test_worktree(self, mock_run):
        # Worktree: git-common-dir points to the main repo's .git
        mock_run.return_value = _mock_run(
            "/Users/me/myrepo-wt",
            "/Users/me/myrepo/.git",
            "feature-branch",
        )
        repo_root, branch, is_wt = get_git_info("/Users/me/myrepo-wt")
        assert repo_root == "/Users/me/myrepo"
        assert branch == "feature-branch"
        assert is_wt is True

    @patch("flaude.git.subprocess.run")
    def test_detached_head(self, mock_run):
        mock_run.return_value = _mock_run("/Users/me/myrepo", ".git", "HEAD")
        repo_root, branch, is_wt = get_git_info("/Users/me/myrepo")
        assert repo_root == "/Users/me/myrepo"
        assert branch is None
        assert is_wt is False

    @patch("flaude.git.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=2)
        assert get_git_info("/tmp/slow") == (None, None, False)

    @patch("flaude.git.subprocess.run")
    def test_os_error(self, mock_run):
        mock_run.side_effect = OSError("git not found")
        assert get_git_info("/tmp/no-git") == (None, None, False)

    @patch("flaude.git.subprocess.run")
    def test_insufficient_output_lines(self, mock_run):
        result = MagicMock()
        result.returncode = 0
        result.stdout = "/Users/me/myrepo\n.git\n"  # only 2 lines
        mock_run.return_value = result
        assert get_git_info("/Users/me/myrepo") == (None, None, False)
