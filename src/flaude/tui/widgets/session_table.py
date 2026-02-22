"""Session list widget — DataTable of active Claude Code sessions."""

from pathlib import Path

from rich.text import Text
from textual.widgets import DataTable

from flaude.constants import utcnow, get_model_limit
from flaude.formatting import format_uptime, format_compact_duration, format_token_count
from flaude.state.models import SessionState, SessionStatus, STATUS_INDICATORS

# Maps status -> (label, theme_var, bold)
STATUS_THEME = {
    SessionStatus.NEW: ("NEW", "accent", True),
    SessionStatus.WORKING: ("RUNNING", "success", True),
    SessionStatus.IDLE: ("IDLE", "text-muted", False),
    SessionStatus.WAITING_PERMISSION: ("PERMISSION", "warning", True),
    SessionStatus.WAITING_ANSWER: ("INPUT", "accent", True),
    SessionStatus.ERROR: ("ERROR", "error", True),
    SessionStatus.ENDED: ("ENDED", "text-muted", False),
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
            self.add_row(
                Text("No sessions", style="dim"),
                "",
                Text(
                    "press n or start claude (flaude init if hooks not set up)",
                    style="dim italic",
                ),
                "",
                "",
                "",
                "",
            )
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
        css = self.app.get_css_variables()
        restore_row = 0
        for idx, state in enumerate(sorted_sessions):
            label, theme_var, bold = STATUS_THEME.get(
                state.status, ("?", "text-muted", False)
            )
            # Differentiate plan approval from input questions
            if state.status == SessionStatus.WAITING_ANSWER and state.is_plan_approval:
                label = "PLAN"
                theme_var = "warning"
            color = css.get(theme_var, "")
            style = f"{color} bold" if bold else color
            if state.status == SessionStatus.WORKING and state.turn_started_at:
                duration = format_compact_duration(now, state.turn_started_at)
            else:
                duration = format_compact_duration(now, state.last_event_at)
            indicator = (
                "📋" if label == "PLAN" else STATUS_INDICATORS.get(state.status, "●")
            )
            status_text = Text(f"{indicator} {label} {duration}", style=style)
            project = Path(state.cwd).name if state.cwd else "?"
            uptime = format_uptime(now, state.started_at)
            term = state.terminal or "?"
            mode = state.permission_mode
            context = _format_context(state.context_tokens, state.model, css)

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

        self.border_subtitle = f" {len(sorted_sessions)} active "

        # Restore cursor to previously selected row
        if self.row_count > 0:
            self.move_cursor(row=restore_row)

    def get_selected_session_id(self) -> str | None:
        """Return the session_id of the currently highlighted row."""
        if self.row_count == 0:
            return None
        row_key, _ = self.coordinate_to_cell_key(self.cursor_coordinate)
        return str(row_key.value) if row_key else None


def _format_context(tokens: int, model: str | None, css: dict) -> Text:
    if tokens <= 0:
        return Text("─", style=css.get("text-muted", "dim"))
    label = format_token_count(tokens)
    limit = get_model_limit(model)
    ratio = tokens / limit if limit else 0
    if ratio > 0.8:
        style = f"{css.get('error', 'red')} bold"
    elif ratio > 0.5:
        style = css.get("warning", "yellow")
    else:
        style = css.get("success", "green")
    return Text(label, style=style)
