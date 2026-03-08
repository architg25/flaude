"""Loop manager panel — shows scheduled tasks across all sessions."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

from flaude.constants import TUI_REFRESH_INTERVAL
from flaude.state.models import SessionState
from flaude.tools import trunc

# Row keys use this prefix for session group headers
_SESSION_PREFIX = "__loop_session__"


class LoopPanel(ModalScreen[str | None]):
    """Modal panel showing loops grouped by session.

    Dismisses with a session_id when Enter is pressed on a loop row,
    or None when closed via Escape/L.
    """

    BINDINGS = [
        Binding("escape", "dismiss_panel", "Close"),
        Binding("L", "dismiss_panel", "Close", show=False),
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
    .loop-empty {
        color: $text-muted;
        text-align: center;
        margin-top: 1;
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

    def __init__(self, get_sessions: callable) -> None:
        super().__init__()
        self._get_sessions = get_sessions

    def compose(self) -> ComposeResult:
        with Vertical(id="loop-dialog"):
            yield Static("Loops", id="loop-title")
            table = DataTable(id="loop-table", cursor_type="row")
            table.add_columns("Session", "ID", "Schedule", "Type", "Prompt")
            yield table
            yield Static("", id="loop-prompt")
            yield Static(
                "[bold]Enter[/] Go to session  [bold]L[/]/[bold]Esc[/] Close",
                id="loop-hint",
            )

    def on_mount(self) -> None:
        self._refresh()
        self.set_interval(TUI_REFRESH_INTERVAL * 2, self._refresh)

    def _refresh(self) -> None:
        table = self.query_one(DataTable)
        sessions = self._get_sessions()

        # Build flat list of rows: (session_id, row_key, cells, full_prompt)
        rows: list[tuple[str, str, tuple, str]] = []
        sessions_with_loops = {sid: s for sid, s in sessions.items() if s.loops}

        for sid, session in sessions_with_loops.items():
            project = _project_name(session)
            for i, loop in enumerate(session.loops.values()):
                marker = "↻" if loop.recurring else "①"
                cron = loop.cron_expr or loop.human_schedule
                # Show session name only on first row of each group
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
                    )
                )

        # Preserve cursor position across refreshes
        old_cursor_row = table.cursor_row

        table.clear()

        if not rows:
            total = len(sessions)
            if total:
                table.add_row(f"No active loops ({total} sessions)", "", "", "", "")
            else:
                table.add_row("No active loops", "", "", "", "")
            return

        self._row_session_map: dict[str, str] = {}
        self._row_prompt_map: dict[str, str] = {}
        for sid, row_key, cells, full_prompt in rows:
            table.add_row(*cells, key=row_key)
            self._row_session_map[row_key] = sid
            self._row_prompt_map[row_key] = full_prompt

        # Restore cursor position
        if old_cursor_row > 0 and old_cursor_row < table.row_count:
            table.move_cursor(row=old_cursor_row)

        sessions_without = len(sessions) - len(sessions_with_loops)
        if sessions_without:
            noun = "session" if sessions_without == 1 else "sessions"
            table.add_row(
                f"No loops: {sessions_without} other {noun}",
                "",
                "",
                "",
                "",
                key="__footer__",
            )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = str(event.row_key.value) if event.row_key else ""
        prompt = getattr(self, "_row_prompt_map", {}).get(key, "")
        label = self.query_one("#loop-prompt", Static)
        if prompt:
            label.update(f"[dim]Prompt:[/] [italic]{prompt}[/]")
        else:
            label.update("")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = str(event.row_key.value) if event.row_key else ""
        session_id = getattr(self, "_row_session_map", {}).get(key)
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
