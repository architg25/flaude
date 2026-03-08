"""Loop manager panel — shows scheduled tasks across all sessions."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

from flaude.constants import TUI_REFRESH_INTERVAL
from flaude.state.models import SessionState, SessionStatus
from flaude.tools import trunc


class LoopPanel(ModalScreen[str | None]):
    """Modal panel showing loops grouped by session.

    Dismisses with a session_id when Enter is pressed on a loop row,
    or None when closed via Escape/L.
    """

    BINDINGS = [
        Binding("escape", "dismiss_panel", "Close"),
        Binding("L", "dismiss_panel", "Close", show=False),
        Binding("x", "cancel_loop", "Cancel Loop"),
        Binding("X", "cancel_all_loops", "Cancel All"),
    ]

    DEFAULT_CSS = """
    LoopPanel {
        align: center middle;
    }
    #loop-dialog {
        width: 80;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    #loop-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    #loop-table {
        height: auto;
        max-height: 50;
    }
    #loop-prompt {
        margin-top: 1;
        padding: 0 1;
        height: auto;
        max-height: 4;
    }
    #loop-hint {
        color: $text-muted;
        text-align: center;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        get_sessions: Callable[[], dict[str, SessionState]],
        send_to_session: Callable[[str, str], bool],
    ) -> None:
        super().__init__()
        self._get_sessions = get_sessions
        self._send_to_session = send_to_session
        self._row_session_map: dict[str, str] = {}
        self._row_prompt_map: dict[str, str] = {}
        self._row_task_id_map: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="loop-dialog"):
            yield Static("Loops", id="loop-title")
            table = DataTable(id="loop-table", cursor_type="row")
            table.add_columns("Session", "ID", "Schedule", "Type", "Prompt")
            yield table
            yield Static("", id="loop-prompt")
            yield Static(
                "[bold]Enter[/] Go to session  "
                "[bold]x[/] Cancel loop  [bold]X[/] Cancel all  "
                "[bold]L[/]/[bold]Esc[/] Close",
                id="loop-hint",
            )

    def on_mount(self) -> None:
        self._refresh()
        self.set_interval(TUI_REFRESH_INTERVAL * 2, self._refresh)

    def _refresh(self) -> None:
        table = self.query_one(DataTable)
        sessions = self._get_sessions()

        # Build flat list of rows: (session_id, row_key, cells, full_prompt, task_id)
        rows: list[tuple[str, str, tuple, str, str]] = []
        sessions_with_loops = {sid: s for sid, s in sessions.items() if s.loops}

        for sid, session in sessions_with_loops.items():
            project = _project_name(session)
            for i, loop in enumerate(session.loops.values()):
                marker = "↻" if loop.recurring else "①"
                cron = loop.cron_expr or loop.human_schedule
                session_col = f"{project} ({sid[:8]})" if i == 0 else ""
                row_key = f"{sid}:{loop.task_id}"
                rows.append(
                    (
                        sid,
                        row_key,
                        (
                            session_col,
                            loop.task_id,
                            cron,
                            marker,
                            trunc(loop.prompt, 40),
                        ),
                        loop.prompt,
                        loop.task_id,
                    )
                )

        old_cursor_row = table.cursor_row

        table.clear()

        if not rows:
            total = len(sessions)
            if total:
                table.add_row(f"No active loops ({total} sessions)", "", "", "", "")
            else:
                table.add_row("No active loops", "", "", "", "")
            return

        self._row_session_map = {}
        self._row_prompt_map = {}
        self._row_task_id_map = {}
        for sid, row_key, cells, full_prompt, task_id in rows:
            table.add_row(*cells, key=row_key)
            self._row_session_map[row_key] = sid
            self._row_prompt_map[row_key] = full_prompt
            self._row_task_id_map[row_key] = task_id

        if old_cursor_row > 0 and old_cursor_row < table.row_count:
            table.move_cursor(row=old_cursor_row)

    def _get_highlighted_row_key(self) -> str:
        """Get the row key string of the currently highlighted row."""
        table = self.query_one(DataTable)
        try:
            cursor = table.cursor_coordinate
            cell_key = table.coordinate_to_cell_key(cursor)
            return str(cell_key.row_key.value)
        except Exception:
            return ""

    def _session_can_receive(self, session_id: str) -> SessionState | None:
        """Check if a session can receive text. Returns state or None."""
        sessions = self._get_sessions()
        state = sessions.get(session_id)
        if not state:
            return None
        if state.status not in (SessionStatus.IDLE, SessionStatus.NEW):
            return None
        return state

    def action_cancel_loop(self) -> None:
        key = self._get_highlighted_row_key()
        session_id = self._row_session_map.get(key)
        task_id = self._row_task_id_map.get(key)
        if not session_id or not task_id:
            return

        state = self._session_can_receive(session_id)
        if not state:
            self.app.notify("Session is busy or unavailable", severity="warning")
            return

        if self._send_to_session(session_id, f"cancel scheduled task {task_id}"):
            self.app.notify(f"Cancelling {task_id}")
        else:
            self.app.notify("Failed to send cancel", severity="error")

    def action_cancel_all_loops(self) -> None:
        key = self._get_highlighted_row_key()
        session_id = self._row_session_map.get(key)
        if not session_id:
            return

        state = self._session_can_receive(session_id)
        if not state:
            self.app.notify("Session is busy or unavailable", severity="warning")
            return

        if self._send_to_session(session_id, "cancel all scheduled tasks"):
            self.app.notify("Cancelling all loops")
        else:
            self.app.notify("Failed to send cancel", severity="error")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = str(event.row_key.value) if event.row_key else ""
        prompt = self._row_prompt_map.get(key, "")
        label = self.query_one("#loop-prompt", Static)
        if prompt:
            label.update(f"[dim]Prompt:[/] [italic]{prompt}[/]")
        else:
            label.update("")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = str(event.row_key.value) if event.row_key else ""
        session_id = self._row_session_map.get(key)
        if session_id:
            self.dismiss(session_id)

    def action_dismiss_panel(self) -> None:
        self.dismiss(None)


def _project_name(session: SessionState) -> str:
    """Derive a display name for a session."""
    if session.custom_title:
        return session.custom_title
    if session.git_repo_root:
        name = Path(session.git_repo_root).name
        if session.git_branch:
            return f"{name}/{session.git_branch}"
        return name
    if session.cwd:
        return Path(session.cwd).name
    return session.session_id[:8]
