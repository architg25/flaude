"""Tests for flaude.state.scanner — session discovery at TUI startup."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from flaude.state.scanner import (
    _backfill_git_fields,
    _backfill_team_fields,
    _parse_activity_log,
    scan_preexisting_sessions,
)
from helpers import make_state


# ---------------------------------------------------------------------------
# _parse_activity_log
# ---------------------------------------------------------------------------


class TestParseActivityLog:
    """Tests for _parse_activity_log helper."""

    def test_empty_log(self, tmp_path, monkeypatch):
        log = tmp_path / "activity.log"
        log.write_text("", encoding="utf-8")
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        ended, known = _parse_activity_log()
        assert ended == set()
        assert known == set()

    def test_missing_log(self, tmp_path, monkeypatch):
        log = tmp_path / "does_not_exist.log"
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        ended, known = _parse_activity_log()
        assert ended == set()
        assert known == set()

    def test_basic_session_start_and_end(self, tmp_path, monkeypatch):
        log = tmp_path / "activity.log"
        log.write_text(
            "2026-02-28T16:18:07 [aabbccdd] SessionStart\n"
            "2026-02-28T16:20:00 [aabbccdd] PreToolUse Bash\n"
            "2026-02-28T16:25:00 [aabbccdd] SessionEnd\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        ended, known = _parse_activity_log()
        assert "aabbccdd" in ended
        assert "aabbccdd" in known

    def test_session_resumed_after_end(self, tmp_path, monkeypatch):
        """SessionStart after SessionEnd means session is no longer ended."""
        log = tmp_path / "activity.log"
        log.write_text(
            "2026-02-28T16:18:07 [aabbccdd] SessionEnd\n"
            "2026-02-28T16:30:00 [aabbccdd] SessionStart\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        ended, known = _parse_activity_log()
        assert "aabbccdd" not in ended
        assert "aabbccdd" in known

    def test_multiple_sessions(self, tmp_path, monkeypatch):
        log = tmp_path / "activity.log"
        log.write_text(
            "2026-02-28T16:00:00 [aaaaaaaa] SessionStart\n"
            "2026-02-28T16:00:00 [bbbbbbbb] SessionStart\n"
            "2026-02-28T16:10:00 [aaaaaaaa] SessionEnd\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        ended, known = _parse_activity_log()
        assert "aaaaaaaa" in ended
        assert "bbbbbbbb" not in ended
        assert known == {"aaaaaaaa", "bbbbbbbb"}

    def test_malformed_lines_skipped(self, tmp_path, monkeypatch):
        log = tmp_path / "activity.log"
        log.write_text(
            "this line has no brackets at all\n"
            "half [bracket but no close\n"
            "2026-02-28T16:00:00 [cccccccc] SessionStart\n"
            "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        ended, known = _parse_activity_log()
        assert known == {"cccccccc"}

    def test_session_end_embedded_in_tool_output_not_matched(
        self, tmp_path, monkeypatch
    ):
        """A line like PreToolUse Bash '...SessionEnd...' should NOT mark ended."""
        log = tmp_path / "activity.log"
        log.write_text(
            "2026-02-28T16:00:00 [dddddddd] SessionStart\n"
            '2026-02-28T16:05:00 [dddddddd] PreToolUse Bash "grep SessionEnd"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        ended, known = _parse_activity_log()
        assert "dddddddd" not in ended
        assert "dddddddd" in known

    def test_duplicate_entries(self, tmp_path, monkeypatch):
        log = tmp_path / "activity.log"
        log.write_text(
            "2026-02-28T16:00:00 [eeeeeeee] SessionStart\n"
            "2026-02-28T16:00:01 [eeeeeeee] SessionStart\n"
            "2026-02-28T16:10:00 [eeeeeeee] PreToolUse Bash\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        ended, known = _parse_activity_log()
        assert "eeeeeeee" not in ended
        assert "eeeeeeee" in known


# ---------------------------------------------------------------------------
# scan_preexisting_sessions
# ---------------------------------------------------------------------------


class TestScanPreexistingSessions:
    """Tests for scan_preexisting_sessions."""

    def _setup_transcript(
        self, projects_dir, project_name, session_id, cwd, timestamp=None, **extra
    ):
        """Create a fake transcript .jsonl file with a first-line entry."""
        project_path = projects_dir / project_name
        project_path.mkdir(parents=True, exist_ok=True)
        transcript = project_path / f"{session_id}.jsonl"
        entry = {"cwd": cwd}
        if timestamp:
            entry["timestamp"] = timestamp
        entry.update(extra)
        transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        return transcript

    def test_no_projects_dir(self, mgr, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "flaude.state.scanner._CLAUDE_PROJECTS_DIR",
            tmp_path / "nonexistent",
        )
        assert scan_preexisting_sessions(mgr) == 0

    def test_no_active_processes(self, mgr, monkeypatch, tmp_path):
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        monkeypatch.setattr("flaude.state.scanner._CLAUDE_PROJECTS_DIR", projects_dir)
        with patch("flaude.state.scanner._get_active_cwds", return_value=set()):
            assert scan_preexisting_sessions(mgr) == 0

    def test_discovers_running_session(self, mgr, monkeypatch, tmp_path):
        projects_dir = tmp_path / "projects"
        sid = "aabbccdd12345678"
        short_id = sid[:8]
        cwd = "/home/user/myrepo"

        self._setup_transcript(
            projects_dir,
            "myproject",
            sid,
            cwd,
            timestamp="2026-03-05T10:00:00Z",
        )

        monkeypatch.setattr("flaude.state.scanner._CLAUDE_PROJECTS_DIR", projects_dir)

        # Activity log: session known but not ended
        log = tmp_path / "activity.log"
        log.write_text(
            f"2026-03-05T10:00:00 [{short_id}] SessionStart\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        with (
            patch(
                "flaude.state.scanner._get_active_cwds",
                return_value={cwd},
            ),
            patch(
                "flaude.state.scanner.get_git_info",
                return_value=("/home/user/myrepo", "main", False),
            ),
        ):
            count = scan_preexisting_sessions(mgr)

        assert count == 1
        state = mgr.load_session(sid)
        assert state is not None
        assert state.cwd == cwd
        assert state.last_event == "Discovered"
        assert state.git_branch == "main"

    def test_skips_already_known_session(self, mgr, monkeypatch, tmp_path):
        projects_dir = tmp_path / "projects"
        sid = "aabbccdd12345678"
        short_id = sid[:8]
        cwd = "/home/user/myrepo"

        self._setup_transcript(projects_dir, "myproject", sid, cwd)

        # Pre-save the session so it's already tracked
        mgr.save_session(make_state(session_id=sid, cwd=cwd))

        monkeypatch.setattr("flaude.state.scanner._CLAUDE_PROJECTS_DIR", projects_dir)
        log = tmp_path / "activity.log"
        log.write_text(
            f"2026-03-05T10:00:00 [{short_id}] SessionStart\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        with patch(
            "flaude.state.scanner._get_active_cwds",
            return_value={cwd},
        ):
            count = scan_preexisting_sessions(mgr)

        assert count == 0

    def test_skips_ended_session(self, mgr, monkeypatch, tmp_path):
        projects_dir = tmp_path / "projects"
        sid = "eennddee12345678"
        short_id = sid[:8]
        cwd = "/home/user/myrepo"

        self._setup_transcript(projects_dir, "myproject", sid, cwd)

        monkeypatch.setattr("flaude.state.scanner._CLAUDE_PROJECTS_DIR", projects_dir)
        log = tmp_path / "activity.log"
        log.write_text(
            f"2026-03-05T10:00:00 [{short_id}] SessionStart\n"
            f"2026-03-05T10:30:00 [{short_id}] SessionEnd\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        with patch(
            "flaude.state.scanner._get_active_cwds",
            return_value={cwd},
        ):
            count = scan_preexisting_sessions(mgr)

        assert count == 0

    def test_skips_session_not_in_activity_log(self, mgr, monkeypatch, tmp_path):
        """Sessions with no activity log entries (predates hooks) are skipped."""
        projects_dir = tmp_path / "projects"
        sid = "unknownn12345678"
        cwd = "/home/user/myrepo"

        self._setup_transcript(projects_dir, "myproject", sid, cwd)

        monkeypatch.setattr("flaude.state.scanner._CLAUDE_PROJECTS_DIR", projects_dir)
        log = tmp_path / "activity.log"
        log.write_text("", encoding="utf-8")
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        with patch(
            "flaude.state.scanner._get_active_cwds",
            return_value={cwd},
        ):
            count = scan_preexisting_sessions(mgr)

        assert count == 0

    def test_skips_stale_transcript(self, mgr, monkeypatch, tmp_path):
        """Transcripts older than STALE_SESSION_TIMEOUT are skipped."""
        projects_dir = tmp_path / "projects"
        sid = "oldoldol12345678"
        short_id = sid[:8]
        cwd = "/home/user/myrepo"

        transcript = self._setup_transcript(projects_dir, "myproject", sid, cwd)
        # Set mtime to be very old
        import os

        old_time = time.time() - 100000
        os.utime(transcript, (old_time, old_time))

        monkeypatch.setattr("flaude.state.scanner._CLAUDE_PROJECTS_DIR", projects_dir)
        log = tmp_path / "activity.log"
        log.write_text(
            f"2026-03-05T10:00:00 [{short_id}] SessionStart\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        with patch(
            "flaude.state.scanner._get_active_cwds",
            return_value={cwd},
        ):
            count = scan_preexisting_sessions(mgr)

        assert count == 0

    def test_skips_subagent_transcripts(self, mgr, monkeypatch, tmp_path):
        """Transcripts under a subagents/ directory are ignored."""
        projects_dir = tmp_path / "projects"
        sid = "subagent12345678"
        cwd = "/home/user/myrepo"

        # Create transcript in a subagents subdirectory
        subagent_dir = projects_dir / "myproject" / "subagents"
        subagent_dir.mkdir(parents=True)
        transcript = subagent_dir / f"{sid}.jsonl"
        transcript.write_text(json.dumps({"cwd": cwd}) + "\n", encoding="utf-8")

        monkeypatch.setattr("flaude.state.scanner._CLAUDE_PROJECTS_DIR", projects_dir)
        log = tmp_path / "activity.log"
        log.write_text(
            f"2026-03-05T10:00:00 [{sid[:8]}] SessionStart\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        with patch(
            "flaude.state.scanner._get_active_cwds",
            return_value={cwd},
        ):
            count = scan_preexisting_sessions(mgr)

        # glob("*/*.jsonl") won't match subagents/X.jsonl anyway,
        # but verify no crash and count is 0
        assert count == 0

    def test_skips_cwd_not_in_active_processes(self, mgr, monkeypatch, tmp_path):
        """Transcripts whose cwd doesn't match any active process are skipped."""
        projects_dir = tmp_path / "projects"
        sid = "mismatch12345678"
        short_id = sid[:8]

        self._setup_transcript(projects_dir, "myproject", sid, "/home/user/inactive")

        monkeypatch.setattr("flaude.state.scanner._CLAUDE_PROJECTS_DIR", projects_dir)
        log = tmp_path / "activity.log"
        log.write_text(
            f"2026-03-05T10:00:00 [{short_id}] SessionStart\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        with patch(
            "flaude.state.scanner._get_active_cwds",
            return_value={"/home/user/active"},
        ):
            count = scan_preexisting_sessions(mgr)

        assert count == 0

    def test_discovers_session_with_team_metadata(self, mgr, monkeypatch, tmp_path):
        projects_dir = tmp_path / "projects"
        sid = "teamteam12345678"
        short_id = sid[:8]
        cwd = "/home/user/myrepo"

        self._setup_transcript(
            projects_dir,
            "myproject",
            sid,
            cwd,
            timestamp="2026-03-05T10:00:00Z",
            teamName="alpha-team",
            agentName="worker-1",
        )

        # Create team config
        teams_dir = tmp_path / "teams" / "alpha-team"
        teams_dir.mkdir(parents=True)
        config = teams_dir / "config.json"
        config.write_text(
            json.dumps({"leadSessionId": "lead12345678"}), encoding="utf-8"
        )

        monkeypatch.setattr("flaude.state.scanner._CLAUDE_PROJECTS_DIR", projects_dir)
        log = tmp_path / "activity.log"
        log.write_text(
            f"2026-03-05T10:00:00 [{short_id}] SessionStart\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("flaude.state.scanner.ACTIVITY_LOG", log)

        # Patch the team config path expansion to use tmp_path
        orig_expanduser = Path.expanduser

        def fake_expanduser(self):
            s = str(self)
            if s.startswith("~/.claude/teams/"):
                return tmp_path / s.removeprefix("~/.claude/")
            return orig_expanduser(self)

        monkeypatch.setattr(Path, "expanduser", fake_expanduser)

        with (
            patch(
                "flaude.state.scanner._get_active_cwds",
                return_value={cwd},
            ),
            patch(
                "flaude.state.scanner.get_git_info",
                return_value=(None, None, False),
            ),
        ):
            count = scan_preexisting_sessions(mgr)

        assert count == 1
        state = mgr.load_session(sid)
        assert state.team_name == "alpha-team"
        assert state.agent_name == "worker-1"
        assert state.lead_session_id == "lead12345678"


# ---------------------------------------------------------------------------
# _backfill_team_fields
# ---------------------------------------------------------------------------


class TestBackfillTeamFields:
    """Tests for _backfill_team_fields."""

    def test_skips_session_with_existing_team(self, mgr, tmp_path):
        """Sessions that already have team_name are not touched."""
        state = make_state(
            session_id="has-team",
            team_name="existing-team",
            transcript_path=str(tmp_path / "fake.jsonl"),
        )
        mgr.save_session(state)

        _backfill_team_fields(mgr)

        reloaded = mgr.load_session("has-team")
        assert reloaded.team_name == "existing-team"

    def test_skips_session_without_transcript(self, mgr):
        """Sessions with no transcript_path are skipped."""
        state = make_state(session_id="no-transcript", transcript_path=None)
        mgr.save_session(state)

        _backfill_team_fields(mgr)

        reloaded = mgr.load_session("no-transcript")
        assert reloaded.team_name is None

    def test_backfills_team_from_transcript(self, mgr, tmp_path):
        transcript = tmp_path / "sess.jsonl"
        transcript.write_text(
            json.dumps({"teamName": "backfilled-team", "agentName": "agent-x"}) + "\n",
            encoding="utf-8",
        )

        state = make_state(
            session_id="needs-team",
            transcript_path=str(transcript),
        )
        mgr.save_session(state)

        _backfill_team_fields(mgr)

        reloaded = mgr.load_session("needs-team")
        assert reloaded.team_name == "backfilled-team"
        assert reloaded.agent_name == "agent-x"

    def test_no_team_in_transcript(self, mgr, tmp_path):
        """Transcript without teamName leaves session unchanged."""
        transcript = tmp_path / "sess.jsonl"
        transcript.write_text(
            json.dumps({"cwd": "/some/path"}) + "\n",
            encoding="utf-8",
        )

        state = make_state(
            session_id="no-team-data",
            transcript_path=str(transcript),
        )
        mgr.save_session(state)

        _backfill_team_fields(mgr)

        reloaded = mgr.load_session("no-team-data")
        assert reloaded.team_name is None

    def test_corrupt_transcript_handled(self, mgr, tmp_path):
        """Corrupt transcript file doesn't crash the backfill."""
        transcript = tmp_path / "bad.jsonl"
        transcript.write_text("not valid json{{{", encoding="utf-8")

        state = make_state(
            session_id="bad-transcript",
            transcript_path=str(transcript),
        )
        mgr.save_session(state)

        # Should not raise
        _backfill_team_fields(mgr)

        reloaded = mgr.load_session("bad-transcript")
        assert reloaded.team_name is None


# ---------------------------------------------------------------------------
# _backfill_git_fields
# ---------------------------------------------------------------------------


class TestBackfillGitFields:
    """Tests for _backfill_git_fields."""

    def test_skips_session_with_existing_git_root(self, mgr):
        state = make_state(
            session_id="has-git",
            cwd="/some/repo",
            git_repo_root="/some/repo",
            git_branch="main",
        )
        mgr.save_session(state)

        with patch("flaude.state.scanner.get_git_info") as mock_git:
            _backfill_git_fields(mgr)
            mock_git.assert_not_called()

    def test_skips_session_without_cwd(self, mgr):
        state = make_state(session_id="no-cwd", cwd="")
        mgr.save_session(state)

        with patch("flaude.state.scanner.get_git_info") as mock_git:
            _backfill_git_fields(mgr)
            mock_git.assert_not_called()

    def test_backfills_git_info(self, mgr):
        state = make_state(
            session_id="needs-git",
            cwd="/home/user/myrepo",
        )
        mgr.save_session(state)

        with patch(
            "flaude.state.scanner.get_git_info",
            return_value=("/home/user/myrepo", "feature-branch", True),
        ):
            _backfill_git_fields(mgr)

        reloaded = mgr.load_session("needs-git")
        assert reloaded.git_repo_root == "/home/user/myrepo"
        assert reloaded.git_branch == "feature-branch"
        assert reloaded.git_is_worktree is True

    def test_no_git_repo_leaves_fields_unset(self, mgr):
        """If get_git_info returns (None, None, False), don't save anything."""
        state = make_state(
            session_id="not-a-repo",
            cwd="/tmp/random",
        )
        mgr.save_session(state)

        with patch(
            "flaude.state.scanner.get_git_info",
            return_value=(None, None, False),
        ):
            _backfill_git_fields(mgr)

        reloaded = mgr.load_session("not-a-repo")
        assert reloaded.git_repo_root is None
