"""Activity log widget — transcript viewer with toggleable verbosity."""

import json
from pathlib import Path

from textual.widgets import RichLog

from flaude.constants import ACTIVITY_LOG

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

    @property
    def mode(self) -> str:
        return self._mode

    def on_mount(self) -> None:
        self.border_title = f"Activity ({MODE_LABELS[self._mode]})"

    def set_session_filter(self, session_id: str | None) -> None:
        prefix = session_id[:8] if session_id else None
        if prefix == self._session_filter:
            return
        self._session_filter = prefix
        # Reset on session change
        self.clear()
        self._tools_last_size = 0
        self._transcript_last_size = 0

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
        self.border_title = f"Activity ({MODE_LABELS[self._mode]})"
        # Reload from scratch with new mode
        self.clear()
        self._tools_last_size = 0
        self._transcript_last_size = 0
        self.refresh_log()

    def refresh_log(self) -> None:
        if self._mode == "tools":
            self._load_tools_log()
        else:
            self._load_transcript()

    def _load_tools_log(self) -> None:
        """Load new lines from the hook activity log (tools mode)."""
        if not ACTIVITY_LOG.exists():
            return
        try:
            size = ACTIVITY_LOG.stat().st_size
            if size <= self._tools_last_size:
                return
            with open(ACTIVITY_LOG) as f:
                f.seek(self._tools_last_size)
                new_content = f.read()
                self._tools_last_size = f.tell()
            for line in new_content.strip().splitlines():
                if self._session_filter and f"[{self._session_filter}]" not in line:
                    continue
                self.write(line)
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
            if size <= self._transcript_last_size:
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

        entry_type = entry.get("type")
        message = entry.get("message", {})
        content = message.get("content", [])

        if entry_type == "progress":
            return None

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
                    return f"[bold]Claude:[/] {truncated}"
                elif role == "user":
                    truncated = text[:max_len] + ("..." if len(text) > max_len else "")
                    return f"[dim]> {truncated}[/]"

            elif item_type == "tool_use":
                name = item.get("name", "?")
                tool_input = item.get("input", {})
                summary = _summarize_tool_input(name, tool_input)
                return f"[bold cyan][tool][/] {name}: {summary}"

            elif item_type == "tool_result":
                continue

        return None


def _summarize_tool_input(name: str, tool_input: dict) -> str:
    if name == "Bash":
        return (tool_input.get("command", ""))[:60]
    if name in ("Edit", "Write", "Read", "MultiEdit"):
        path = tool_input.get("file_path", "")
        return path.rsplit("/", 1)[-1] if path else ""
    if name == "Grep":
        return tool_input.get("pattern", "")[:40]
    if name == "Glob":
        return tool_input.get("pattern", "")
    if name == "Task":
        return tool_input.get("prompt", "")[:40]
    return ""
