"""Tests for version_check.py — version parsing, comparison, caching, and remote fetch."""

import subprocess
from datetime import UTC, datetime, timedelta

import pytest

from flaude.version_check import (
    _version_tuple,
    check_for_update,
    fetch_remote_version,
)


# ---------------------------------------------------------------------------
# _version_tuple
# ---------------------------------------------------------------------------


class TestVersionTuple:
    def test_simple(self):
        assert _version_tuple("1.2.3") == (1, 2, 3)

    def test_zero_prefix(self):
        assert _version_tuple("0.12.4") == (0, 12, 4)

    def test_two_parts(self):
        assert _version_tuple("3.7") == (3, 7)

    def test_single_part(self):
        assert _version_tuple("42") == (42,)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _version_tuple("abc.def")


# ---------------------------------------------------------------------------
# fetch_remote_version  (mocked subprocess)
# ---------------------------------------------------------------------------


class TestFetchRemoteVersion:
    def test_tags_success(self, monkeypatch):
        """Return highest version from remote tags."""
        stdout = (
            "abc123\trefs/tags/v0.10.0\n"
            "def456\trefs/tags/v0.12.4\n"
            "ghi789\trefs/tags/v0.11.0\n"
        )

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert fetch_remote_version() == "0.12.4"

    def test_fail_returns_none(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert fetch_remote_version() is None

    def test_tags_with_peeled_refs(self, monkeypatch):
        """Tags that end with ^{} should be handled correctly."""
        stdout = "abc\trefs/tags/v2.0.0\n" "def\trefs/tags/v2.0.0^{}\n"

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert fetch_remote_version() == "2.0.0"


# ---------------------------------------------------------------------------
# check_for_update  (mocked subprocess + version)
# ---------------------------------------------------------------------------


class TestCheckForUpdate:
    def test_skips_when_recently_checked(self, monkeypatch):
        """If last_check was within 24h, don't call fetch_remote_version."""
        import flaude.version_check as vc

        monkeypatch.setattr(vc, "__version__", "0.10.0")

        config = {
            "update_check": {
                "last_check": datetime.now(UTC).isoformat(),
                "remote_version": "0.12.0",
            }
        }
        # Remote is newer (minor bump) and cache is fresh -> return cached result
        result = check_for_update(config)
        assert result == ("0.10.0", "0.12.0")

    def test_cache_same_version_returns_none(self, monkeypatch):
        """Cached remote == local -> no update."""
        import flaude.version_check as vc

        monkeypatch.setattr(vc, "__version__", "0.12.4")

        config = {
            "update_check": {
                "last_check": datetime.now(UTC).isoformat(),
                "remote_version": "0.12.4",
            }
        }
        assert check_for_update(config) is None

    def test_cache_only_patch_returns_none(self, monkeypatch):
        """Only a patch bump (same minor) should not trigger update notice."""
        import flaude.version_check as vc

        monkeypatch.setattr(vc, "__version__", "0.12.0")

        config = {
            "update_check": {
                "last_check": datetime.now(UTC).isoformat(),
                "remote_version": "0.12.9",
            }
        }
        assert check_for_update(config) is None

    def test_expired_cache_fetches_fresh(self, monkeypatch):
        """If last_check > 24h ago, re-fetch from remote."""
        import flaude.version_check as vc

        monkeypatch.setattr(vc, "__version__", "0.10.0")
        monkeypatch.setattr(vc, "fetch_remote_version", lambda: "0.13.0")

        old_time = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        config = {
            "update_check": {
                "last_check": old_time,
                "remote_version": "0.10.0",
            }
        }
        result = check_for_update(config)
        assert result == ("0.10.0", "0.13.0")
        # Cache should be refreshed
        assert config["update_check"]["remote_version"] == "0.13.0"

    def test_empty_config(self, monkeypatch):
        """First run with no cache should fetch and store."""
        import flaude.version_check as vc

        monkeypatch.setattr(vc, "__version__", "0.10.0")
        monkeypatch.setattr(vc, "fetch_remote_version", lambda: "0.12.0")

        config = {}
        result = check_for_update(config)
        assert result == ("0.10.0", "0.12.0")
        assert "update_check" in config
        assert config["update_check"]["remote_version"] == "0.12.0"

    def test_remote_fetch_returns_none(self, monkeypatch):
        """When remote is unreachable, return None and cache None."""
        import flaude.version_check as vc

        monkeypatch.setattr(vc, "__version__", "0.10.0")
        monkeypatch.setattr(vc, "fetch_remote_version", lambda: None)

        config = {}
        assert check_for_update(config) is None
        assert config["update_check"]["remote_version"] is None

    def test_corrupted_cache_refetches(self, monkeypatch):
        """Corrupted last_check value should trigger a fresh fetch."""
        import flaude.version_check as vc

        monkeypatch.setattr(vc, "__version__", "0.10.0")
        monkeypatch.setattr(vc, "fetch_remote_version", lambda: "0.13.0")

        config = {
            "update_check": {
                "last_check": "not-a-date",
                "remote_version": "0.10.0",
            }
        }
        result = check_for_update(config)
        assert result == ("0.10.0", "0.13.0")
