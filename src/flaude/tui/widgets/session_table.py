"""Session list widget — DataTable of active Claude Code sessions."""

from datetime import datetime
from pathlib import Path

from textual.widgets import DataTable

from flaude.constants import utcnow

from flaude.state.models import SessionState, SessionStatus

STATUS_ICONS = {
    SessionStatus.WORKING: ("▶", "status-working"),
    SessionStatus.IDLE: ("·", "status-idle"),
    SessionStatus.WAITING_PERMISSION: ("!", "status-waiting"),
    SessionStatus.WAITING_ANSWER: ("?", "status-waiting"),
    SessionStatus.ERROR: ("✗", "status-error"),
    SessionStatus.ENDED: ("○", "status-ended"),
}


class SessionTable(DataTable):
    """Table showing all active sessions."""

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.add_columns("ST", "Session", "Project", "Term", "Age", "#")
        self.border_title = "Sessions"

    def update_sessions(self, sessions: dict[str, SessionState]) -> None:
        # Preserve selection across refreshes
        selected_key = self.get_selected_session_id()

        self.clear()

        if not sessions:
            return

        # Sort: waiting first, then working, then idle, then ended
        priority = {
            SessionStatus.WAITING_PERMISSION: 0,
            SessionStatus.WAITING_ANSWER: 0,
            SessionStatus.ERROR: 1,
            SessionStatus.WORKING: 2,
            SessionStatus.IDLE: 3,
            SessionStatus.ENDED: 4,
        }
        sorted_sessions = sorted(
            sessions.values(),
            key=lambda s: (priority.get(s.status, 5), s.started_at),
        )

        now = utcnow()
        restore_row = 0
        for idx, state in enumerate(sorted_sessions):
            icon, css_class = STATUS_ICONS.get(state.status, ("?", "status-idle"))
            project = Path(state.cwd).name if state.cwd else "?"
            age = _format_age(now, state.started_at)
            tool_count = sum(state.tool_stats.values())
            term = state.terminal or "?"

            self.add_row(
                icon,
                state.session_id[:8],
                project[:20],
                term,
                age,
                str(tool_count),
                key=state.session_id,
            )
            if state.session_id == selected_key:
                restore_row = idx

        # Restore cursor to previously selected row
        if self.row_count > 0:
            self.move_cursor(row=restore_row)

    def get_selected_session_id(self) -> str | None:
        """Return the session_id of the currently highlighted row."""
        if self.row_count == 0:
            return None
        row_key, _ = self.coordinate_to_cell_key(self.cursor_coordinate)
        return str(row_key.value) if row_key else None


def _format_age(now: datetime, started: datetime) -> str:
    delta = now - started
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h{minutes % 60}m"
    days = hours // 24
    return f"{days}d{hours % 24}h"
