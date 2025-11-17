"""Main Textual TUI application."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

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
        Binding("y", "approve", "Approve", show=True),
        Binding("n", "deny", "Deny", show=True),
        Binding("a", "approve_all", "Approve All"),
        Binding("g", "goto_session", "Go To"),
        Binding("question_mark", "help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._mgr = StateManager()
        self._terminal = detect_terminal()

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
        # Filter out ended sessions older than 5 minutes for display
        active = {
            sid: s for sid, s in sessions.items() if s.status != SessionStatus.ENDED
        }
        self.query_one(SessionTable).update_sessions(active)
        self.query_one(PermissionPanel).update_permissions(active)
        self.query_one(ActivityLog).refresh_log()

        # Update title with counts
        pending = sum(len(s.pending_permissions) for s in active.values())
        if pending:
            self.title = f"flaude ({len(active)} sessions, {pending} pending)"
        else:
            self.title = f"flaude ({len(active)} sessions)"

    def _cleanup(self) -> None:
        cleanup_stale_sessions(self._mgr)

    def action_approve(self) -> None:
        panel = self.query_one(PermissionPanel)
        if panel.approve_selected(self._mgr):
            self.notify("Approved", severity="information")
            self._refresh_state()
        else:
            self.notify("Nothing to approve", severity="warning")

    def action_deny(self) -> None:
        panel = self.query_one(PermissionPanel)
        if panel.deny_selected(self._mgr):
            self.notify("Denied", severity="warning")
            self._refresh_state()
        else:
            self.notify("Nothing to deny", severity="warning")

    def action_approve_all(self) -> None:
        panel = self.query_one(PermissionPanel)
        count = panel.approve_all(self._mgr)
        if count:
            self.notify(f"Approved {count} permissions", severity="information")
            self._refresh_state()
        else:
            self.notify("Nothing to approve", severity="warning")

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

        if navigate_to_session(self._terminal, state.cwd):
            self.notify(f"Switched to {session_id[:8]}")
        else:
            # Fallback: show resume command
            self.notify(
                f"Could not switch. Resume with: claude --resume {session_id}",
                severity="warning",
                timeout=10,
            )

    def action_help(self) -> None:
        self.notify(
            "[y] Approve  [n] Deny  [a] Approve All  " "[g] Go to session  [q] Quit",
            timeout=10,
        )
