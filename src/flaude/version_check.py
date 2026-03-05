"""Remote version checking with caching.

Checks at most once per 24 hours. Stores last-check timestamp and result
in ~/.config/flaude/config.yaml under an ``update_check`` key.
"""

import re
import subprocess
from datetime import UTC, datetime

from flaude import __version__

_REMOTE = "git@ghe.spotify.net:vibes/flaude.git"
_CHECK_INTERVAL_HOURS = 24


def _version_tuple(v: str) -> tuple[int, ...]:
    # Strip PEP 440 dev/post/local suffixes (e.g. "0.13.1.dev2+ghash")
    v = re.split(r"\.dev|\.post|\+", v)[0]
    return tuple(int(x) for x in v.split("."))


def _fetch_via_tags() -> str | None:
    """Fallback: latest ``v*`` tag from remote."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", _REMOTE],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        versions: list[tuple[int, ...]] = []
        for line in result.stdout.strip().splitlines():
            ref = line.split("\t")[1]
            tag = ref.replace("refs/tags/", "").rstrip("^{}")
            if tag.startswith("v"):
                try:
                    versions.append(_version_tuple(tag[1:]))
                except (ValueError, IndexError):
                    continue
        return ".".join(str(x) for x in max(versions)) if versions else None
    except Exception:
        return None


def fetch_remote_version() -> str | None:
    """Fetch latest version from remote git tags."""
    return _fetch_via_tags()


def check_for_update(config: dict) -> tuple[str, str] | None:
    """Check if a newer version is available, respecting the 24h cache.

    Mutates *config* with cache data — caller must persist.
    Returns ``(current, remote)`` if an update exists, else ``None``.
    """
    cache = config.get("update_check", {})
    last_check = cache.get("last_check")

    if last_check:
        try:
            last_dt = datetime.fromisoformat(last_check)
            elapsed_h = (datetime.now(UTC) - last_dt).total_seconds() / 3600
            if elapsed_h < _CHECK_INTERVAL_HOURS:
                cached = cache.get("remote_version")
                if (
                    cached
                    and _version_tuple(cached)[:2] > _version_tuple(__version__)[:2]
                ):
                    return (__version__, cached)
                return None
        except (ValueError, TypeError):
            pass  # corrupted cache, re-check

    remote = fetch_remote_version()

    config["update_check"] = {
        "last_check": datetime.now(UTC).isoformat(),
        "remote_version": remote,
    }

    if remote and _version_tuple(remote)[:2] > _version_tuple(__version__)[:2]:
        return (__version__, remote)
    return None
