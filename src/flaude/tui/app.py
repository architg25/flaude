"""Main Textual TUI application."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, DataTable

from flaude.state.manager import StateManager
from flaude.state.models import SessionStatus
from flaude.state.cleanup import cleanup_stale_sessions
from flaude.terminal.detect import detect_terminal
from flaude.terminal.navigate import navigate_to_session
from flaude.tui.widgets.session_table import SessionTable
from flaude.tui.widgets.permission_panel import PermissionPanel
from flaude.tui.widgets.activity_log import ActivityLog


class FlaudeApp(App):
    """Claude Code session manager dashboard."""

    CSS_PATH = "app.tcss"
    TITLE = "flaude"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("g", "goto_session", "Go To"),
        Binding("question_mark", "help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._mgr = StateManager()
        self._fallback_terminal = detect_terminal()

    def compose(self) -> ComposeResult:
        yield Header()
        yield SessionTable(id="session-table")
        yield PermissionPanel(id="permission-panel")
        yield ActivityLog(id="activity-log")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(1.0, self._refresh_state)
        self.set_interval(30.0, self._cleanup)
        self._refresh_state()

    def _refresh_state(self) -> None:
        sessions = self._mgr.load_all_sessions()
        active = {
            sid: s for sid, s in sessions.items() if s.status != SessionStatus.ENDED
        }
        table = self.query_one(SessionTable)
        table.update_sessions(active)
        self.query_one(PermissionPanel).update_permissions(active)

        log = self.query_one(ActivityLog)
        log.set_session_filter(table.get_selected_session_id())
        log.refresh_log()

        waiting = sum(
            1
            for s in active.values()
            if s.status
            in (SessionStatus.WAITING_PERMISSION, SessionStatus.WAITING_ANSWER)
        )
        if waiting:
            self.title = f"flaude ({len(active)} sessions, {waiting} waiting)"
        else:
            self.title = f"flaude ({len(active)} sessions)"

    def _cleanup(self) -> None:
        cleanup_stale_sessions(self._mgr)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter on a session row."""
        self.action_goto_session()

    def action_goto_session(self) -> None:
        table = self.query_one(SessionTable)
        session_id = table.get_selected_session_id()
        if not session_id:
            self.notify("No session selected", severity="warning")
            return

        state = self._mgr.load_session(session_id)
        if not state:
            self.notify("Session not found", severity="error")
            return

        # Use per-session terminal if available, fall back to global detection
        terminal = state.terminal or self._fallback_terminal

        if navigate_to_session(terminal, state.cwd):
            self.notify(f"Switched to {session_id[:8]}")
        else:
            self.notify(
                f"Could not switch. Resume with: claude --resume {session_id}",
                severity="warning",
                timeout=10,
            )

    def action_help(self) -> None:
        self.notify(
            "[Enter/g] Go to session  [q] Quit",
            timeout=10,
        )
