"""Activity log widget — scrolling event log, filtered by selected session."""

from textual.widgets import RichLog

from flaude.constants import ACTIVITY_LOG


class ActivityLog(RichLog):
    """Tails the activity log file, filtered to the selected session."""

    def __init__(self, **kwargs) -> None:
        super().__init__(highlight=True, markup=True, max_lines=200, **kwargs)
        self._last_size: int = 0
        self._session_filter: str | None = None

    def on_mount(self) -> None:
        self.border_title = "Activity"
        self._reload_filtered()

    def set_session_filter(self, session_id: str | None) -> None:
        """Set which session to show logs for. None = show all."""
        prefix = session_id[:8] if session_id else None
        if prefix == self._session_filter:
            return
        self._session_filter = prefix
        # Filter changed — clear and reload from scratch
        self.clear()
        self._last_size = 0
        self._reload_filtered()

    def refresh_log(self) -> None:
        """Check for new lines in the activity log."""
        self._load_new_lines()

    def _reload_filtered(self) -> None:
        """Read the full log file and display only matching lines."""
        if not ACTIVITY_LOG.exists():
            return
        try:
            with open(ACTIVITY_LOG) as f:
                content = f.read()
                self._last_size = f.tell()
            for line in content.strip().splitlines():
                if self._matches(line):
                    self.write(line)
        except OSError:
            pass

    def _load_new_lines(self) -> None:
        if not ACTIVITY_LOG.exists():
            return
        try:
            size = ACTIVITY_LOG.stat().st_size
            if size <= self._last_size:
                return

            with open(ACTIVITY_LOG) as f:
                f.seek(self._last_size)
                new_content = f.read()
                self._last_size = f.tell()

            for line in new_content.strip().splitlines():
                if self._matches(line):
                    self.write(line)
        except OSError:
            pass

    def _matches(self, line: str) -> bool:
        if self._session_filter is None:
            return True
        return f"[{self._session_filter}]" in line
