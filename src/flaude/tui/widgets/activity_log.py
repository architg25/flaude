"""Activity log widget — transcript viewer with toggleable verbosity."""

import json
from pathlib import Path

from textual.widgets import RichLog

from flaude.constants import ACTIVITY_LOG, LOGS_DIR
from flaude.tools import summarize_tool

MODES = ["all", "summary", "tools"]
MODE_LABELS = {"all": "All", "summary": "Summary", "tools": "Tools"}


class ActivityLog(RichLog):
    """Tails the session transcript or activity log with configurable detail level."""

    def __init__(self, initial_mode: str = "tools", **kwargs) -> None:
        super().__init__(highlight=True, markup=True, max_lines=500, **kwargs)
        self._mode: str = initial_mode if initial_mode in MODES else "tools"
        self._session_filter: str | None = None
        self._transcript_path: str | None = None
        # Track file position for incremental reads
        self._tools_last_size: int = 0
        self._transcript_last_size: int = 0
        # Per-session activity cache
        self._session_id: str | None = None
        self._cache_path: Path | None = None
        self._cache_last_size: int = 0

    @property
    def mode(self) -> str:
        return self._mode

    def on_mount(self) -> None:
        self.border_title = f"Activity ── {MODE_LABELS[self._mode]}"

    def set_session_id(self, session_id: str | None) -> None:
        """Set the full session ID for cache file lookup."""
        if session_id == self._session_id:
            return
        self._session_id = session_id
        self._cache_path = (
            LOGS_DIR / f"{session_id}.activity.jsonl" if session_id else None
        )
        self._cache_last_size = 0

    def set_session_filter(self, session_id: str | None) -> None:
        prefix = session_id[:8] if session_id else None
        if prefix == self._session_filter:
            return
        self._session_filter = prefix
        # Reset on session change
        self.clear()
        self._tools_last_size = 0
        self._transcript_last_size = 0
        self._cache_last_size = 0

    def set_transcript_path(self, path: str | None) -> None:
        if path == self._transcript_path:
            return
        self._transcript_path = path
        # Reset on path change
        self.clear()
        self._transcript_last_size = 0

    def cycle_mode(self) -> None:
        idx = MODES.index(self._mode)
        self._mode = MODES[(idx + 1) % len(MODES)]
        self.border_title = f"Activity ── {MODE_LABELS[self._mode]}"
        # Reload from scratch with new mode
        self.clear()
        self._tools_last_size = 0
        self._transcript_last_size = 0
        self._cache_last_size = 0
        self.refresh_log()

    def refresh_log(self) -> None:
        if self._mode == "tools":
            self._load_tools_log()
        else:
            self._load_transcript()

    def _load_tools_log(self) -> None:
        """Load from per-session activity cache (fast) or global log (fallback)."""
        if self._cache_path and self._cache_path.exists():
            self._load_from_cache()
        else:
            self._load_from_global_log()

    def _load_from_global_log(self) -> None:
        """Load new lines from the global hook activity log (fallback)."""
        if not ACTIVITY_LOG.exists():
            return
        try:
            size = ACTIVITY_LOG.stat().st_size
            if size < self._tools_last_size:
                # File was truncated (e.g., log rotation) — reset
                self.clear()
                self._tools_last_size = 0
            if size == self._tools_last_size:
                return
            with open(ACTIVITY_LOG) as f:
                f.seek(self._tools_last_size)
                new_content = f.read()
                self._tools_last_size = f.tell()
            for line in new_content.strip().splitlines():
                if self._session_filter and f"[{self._session_filter}]" not in line:
                    continue
                self.write(f"[dim]│[/] {line}")
        except OSError:
            pass

    def _load_from_cache(self) -> None:
        """Load new entries from the per-session activity cache."""
        try:
            size = self._cache_path.stat().st_size
            if size < self._cache_last_size:
                self.clear()
                self._cache_last_size = 0
            if size == self._cache_last_size:
                return
            with open(self._cache_path) as f:
                f.seek(self._cache_last_size)
                new_content = f.read()
                self._cache_last_size = f.tell()
            for line in new_content.strip().splitlines():
                try:
                    entry = json.loads(line)
                    formatted = _format_cache_entry(entry)
                    if formatted:
                        self.write(formatted)
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass

    def _load_transcript(self) -> None:
        """Load new entries from the session transcript JSONL."""
        if not self._transcript_path:
            return
        path = Path(self._transcript_path)
        if not path.exists():
            return
        try:
            size = path.stat().st_size
            if size < self._transcript_last_size:
                # File was truncated — reset
                self.clear()
                self._transcript_last_size = 0
            if size == self._transcript_last_size:
                return
            with open(path) as f:
                f.seek(self._transcript_last_size)
                new_content = f.read()
                self._transcript_last_size = f.tell()
            for line in new_content.strip().splitlines():
                formatted = self._format_transcript_entry(line)
                if formatted:
                    self.write(formatted)
        except OSError:
            pass

    def _format_transcript_entry(self, line: str) -> str | None:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            return None

        if not isinstance(entry, dict):
            return None

        entry_type = entry.get("type")
        message = entry.get("message", {})
        content = message.get("content", [])

        if entry_type == "progress":
            return None

        # User messages have content as a plain string, not a list
        if isinstance(content, str) and message.get("role") == "user":
            if entry.get("isMeta"):
                return None
            text = content.strip()
            if not text or text.startswith(
                ("<command-name>", "<local-command-caveat>", "<system-reminder>")
            ):
                return None
            text = " ".join(text.split())
            max_len = 100 if self._mode == "summary" else 500
            truncated = text[:max_len] + ("..." if len(text) > max_len else "")
            return f"[dim]▸ {truncated}[/]"

        if not isinstance(content, list):
            return None

        is_summary = self._mode == "summary"
        max_len = 100 if is_summary else 500

        for item in content:
            item_type = item.get("type")

            if item_type == "text":
                text = item.get("text", "").strip()
                if not text:
                    continue
                # Collapse whitespace for display
                text = " ".join(text.split())
                role = message.get("role", entry_type)
                if role == "assistant":
                    truncated = text[:max_len] + ("..." if len(text) > max_len else "")
                    return f"◀ [bold]Claude:[/] {truncated}"
                elif role == "user":
                    truncated = text[:max_len] + ("..." if len(text) > max_len else "")
                    return f"[dim]▸ {truncated}[/]"

            elif item_type == "tool_use":
                name = item.get("name", "?")
                tool_input = item.get("input", {})
                summary = summarize_tool(name, tool_input)
                return f"⚙ [cyan bold]{name}[/] [dim]{summary}[/]"

            elif item_type == "tool_result":
                continue

        return None


def _format_cache_entry(entry: dict) -> str | None:
    """Format a per-session activity cache JSONL entry for display."""
    ev = entry.get("ev", "")
    ts = entry.get("ts", "")[11:]  # HH:MM:SS from ISO timestamp
    if ev == "PreToolUse":
        tool = entry.get("tool", "?")
        summary = entry.get("sum", "")
        return f"[dim]{ts}[/] ⚙ [cyan bold]{tool}[/] [dim]{summary}[/]"
    elif ev == "PostToolUse":
        return None  # Don't show post — pre already shows the tool
    elif ev == "UserPrompt":
        text = entry.get("text", "")
        return f"[dim]{ts}[/] [dim]▸ {text}[/]"
    elif ev == "Stop":
        return f"[dim]{ts}[/] [dim]● idle[/]"
    elif ev == "SessionStart":
        return f"[dim]{ts}[/] [bold]◆ session started[/]"
    elif ev == "PermissionRequest":
        tool = entry.get("tool", "?")
        return f"[dim]{ts}[/] ⏳ [yellow]permission[/] {tool}"
    elif ev == "SubagentStop":
        return f"[dim]{ts}[/] [dim]↩ subagent done[/]"
    return None
