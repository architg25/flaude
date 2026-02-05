"""Session list widget — DataTable of active Claude Code sessions."""

from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual.widgets import DataTable

from flaude.constants import utcnow
from flaude.state.models import SessionState, SessionStatus

MODEL_LIMITS = {
    "claude-opus-4-6": 1_000_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5": 200_000,
}
DEFAULT_LIMIT = 200_000

STATUS_LABELS = {
    SessionStatus.NEW: ("NEW", "blue bold"),
    SessionStatus.WORKING: ("RUNNING", "green bold"),
    SessionStatus.IDLE: ("IDLE", "dim"),
    SessionStatus.WAITING_PERMISSION: ("PERMISSION", "yellow bold"),
    SessionStatus.WAITING_ANSWER: ("INPUT", "cyan bold"),
    SessionStatus.ERROR: ("ERROR", "red bold"),
    SessionStatus.ENDED: ("ENDED", "dim"),
}


class SessionTable(DataTable):
    """Table showing all active sessions."""

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.add_columns(
            "Status", "Session", "Project", "Terminal", "Mode", "Context", "Uptime"
        )
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
            SessionStatus.NEW: 2,
            SessionStatus.WORKING: 3,
            SessionStatus.IDLE: 4,
            SessionStatus.ENDED: 5,
        }
        sorted_sessions = sorted(
            sessions.values(),
            key=lambda s: (priority.get(s.status, 5), s.started_at),
        )

        now = utcnow()
        restore_row = 0
        for idx, state in enumerate(sorted_sessions):
            label, style = STATUS_LABELS.get(state.status, ("?", "dim"))
            if state.status == SessionStatus.WORKING and state.turn_started_at:
                duration = _format_compact(now, state.turn_started_at)
            else:
                duration = _format_compact(now, state.last_event_at)
            status_text = Text(f"{label} {duration}", style=style)
            project = Path(state.cwd).name if state.cwd else "?"
            uptime = _format_uptime(now, state.started_at)
            term = state.terminal or "?"
            mode = state.permission_mode
            context = _format_context(state.context_tokens, state.model)

            self.add_row(
                status_text,
                state.session_id[:8],
                project[:20],
                term,
                mode,
                context,
                uptime,
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


def _format_compact(now: datetime, since: datetime) -> str:
    secs = int((now - since).total_seconds())
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m{secs % 60:02d}s"
    hours = mins // 60
    return f"{hours}h{mins % 60:02d}m"


def _format_context(tokens: int, model: str | None) -> Text:
    if tokens <= 0:
        return Text("-", style="dim")
    if tokens >= 1_000_000:
        label = f"{tokens / 1_000_000:.1f}M"
    elif tokens >= 1_000:
        label = f"{tokens // 1_000}K"
    else:
        label = str(tokens)
    limit = MODEL_LIMITS.get(model or "", DEFAULT_LIMIT)
    ratio = tokens / limit if limit else 0
    if ratio > 0.8:
        style = "red bold"
    elif ratio > 0.5:
        style = "yellow"
    else:
        style = "green"
    return Text(label, style=style)


def _format_uptime(now: datetime, started: datetime) -> str:
    delta = now - started
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h{minutes % 60}m"
    days = hours // 24
    return f"{days}d{hours % 24}h"
