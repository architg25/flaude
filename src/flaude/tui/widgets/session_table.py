"""Session list widget — DataTable of active Claude Code sessions."""

from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual.widgets import DataTable

from flaude.constants import utcnow, get_model_limit
from flaude.formatting import format_uptime, format_compact_duration, format_token_count
from flaude.state.models import SessionState, SessionStatus, STATUS_INFO


def _build_row_data(
    state: SessionState, now: datetime, css: dict
) -> tuple[Text, str, str, str, str, Text, str]:
    """Build the 7 cell values for a session row."""
    info = STATUS_INFO[state.status]
    color = css.get(info.theme_var, "")
    style = f"{color} bold" if info.bold else color
    if state.status == SessionStatus.WORKING and state.turn_started_at:
        duration = format_compact_duration(now, state.turn_started_at)
    else:
        duration = format_compact_duration(now, state.last_event_at)
    status_text = Text(f"{info.indicator} {info.label} {duration}", style=style)
    project = Path(state.cwd).name if state.cwd else "?"
    uptime = format_uptime(now, state.started_at)
    term = state.terminal or "?"
    mode = state.permission_mode
    context = _format_context(state.context_tokens, state.model, css)
    return status_text, state.session_id[:8], project[:20], term, mode, context, uptime


class SessionTable(DataTable):
    """Table showing all active sessions."""

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self._col_keys = self.add_columns(
            "Status", "Session", "Project", "Terminal", "Mode", "Context", "Uptime"
        )
        self._last_order: list[str] = []
        self.border_title = "Sessions"

    def update_sessions(
        self, sessions: dict[str, SessionState], hidden_count: int = 0
    ) -> None:
        selected_key = self.get_selected_session_id()

        if not sessions:
            if self._last_order:
                # Transition to empty state
                self.clear()
                self._last_order = []
            if self.row_count == 0:
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

        sorted_sessions = sorted(
            sessions.values(),
            key=lambda s: (STATUS_INFO[s.status].sort_priority, s.started_at),
        )
        new_order = [s.session_id for s in sorted_sessions]

        now = utcnow()
        css = self.app.get_css_variables()

        if new_order == self._last_order:
            # Fast path: in-place cell updates (no DOM teardown)
            for state in sorted_sessions:
                cells = _build_row_data(state, now, css)
                for col_key, value in zip(self._col_keys, cells):
                    self.update_cell(state.session_id, col_key, value)
        else:
            # Slow path: sessions added/removed/reordered — full rebuild
            self.clear()
            for state in sorted_sessions:
                cells = _build_row_data(state, now, css)
                self.add_row(*cells, key=state.session_id)
            self._last_order = new_order

            # Restore cursor to previously selected row
            if selected_key:
                for idx, sid in enumerate(new_order):
                    if sid == selected_key:
                        self.move_cursor(row=idx)
                        break

        if hidden_count:
            self.border_subtitle = (
                f" {len(sorted_sessions)} active ({hidden_count} hidden) "
            )
        else:
            self.border_subtitle = f" {len(sorted_sessions)} active "

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
