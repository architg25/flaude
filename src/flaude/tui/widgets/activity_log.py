"""Activity log widget — scrolling event log."""

from pathlib import Path

from textual.widgets import RichLog

from flaude.constants import ACTIVITY_LOG


class ActivityLog(RichLog):
    """Tails the activity log file and displays recent events."""

    def __init__(self, **kwargs) -> None:
        super().__init__(highlight=True, markup=True, max_lines=200, **kwargs)
        self._last_size: int = 0

    def on_mount(self) -> None:
        self.border_title = "Activity"
        # Load existing lines
        self._load_new_lines()

    def refresh_log(self) -> None:
        """Check for new lines in the activity log."""
        self._load_new_lines()

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
                self.write(line)
        except OSError:
            pass
