"""Main Textual TUI application."""

import os

import yaml
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, DataTable

from flaude.constants import CONFIG_PATH, DEFAULT_THEME
from flaude.state.manager import StateManager
from flaude.state.models import SessionStatus
from flaude.state.cleanup import cleanup_stale_sessions
from flaude.terminal.detect import detect_terminal
from flaude.terminal.navigate import navigate_to_session
from flaude.terminal.process import kill_session
from flaude.tui.screens.confirm import ConfirmScreen
from flaude.tui.widgets.session_table import SessionTable
from flaude.tui.widgets.permission_panel import PermissionPanel
from flaude.tui.widgets.activity_log import ActivityLog


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    return {}


def _save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".yaml.tmp")
    with open(tmp, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    os.rename(tmp, CONFIG_PATH)


class FlaudeApp(App):
    """Claude Code session manager dashboard."""

    CSS_PATH = "app.tcss"
    TITLE = "🤖 flaude"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("g", "goto_session", "Go To"),
        Binding("d", "kill_session", "Kill"),
        Binding("t", "change_theme", "Theme"),
        Binding("question_mark", "help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._mgr = StateManager()
        self._fallback_terminal = detect_terminal()
        self._config = _load_config()
        self.theme = self._config.get("theme", DEFAULT_THEME)

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

    def watch_theme(self, theme: str) -> None:
        """Save theme selection whenever it changes."""
        self._config["theme"] = theme
        try:
            _save_config(self._config)
        except Exception:
            pass

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

        terminal = state.terminal or self._fallback_terminal

        if navigate_to_session(terminal, state.cwd):
            self.notify(f"Switched to {session_id[:8]}")
        else:
            self.notify(
                f"Could not switch. Resume with: claude --resume {session_id}",
                severity="warning",
                timeout=10,
            )

    def action_kill_session(self) -> None:
        table = self.query_one(SessionTable)
        session_id = table.get_selected_session_id()
        if not session_id:
            self.notify("No session selected", severity="warning")
            return

        state = self._mgr.load_session(session_id)
        if not state:
            self.notify("Session not found", severity="error")
            return

        project = state.cwd.rsplit("/", 1)[-1] if state.cwd else session_id[:8]

        def on_confirm(confirmed: bool) -> None:
            if not confirmed:
                return
            if kill_session(state.cwd):
                self._mgr.delete_session(session_id)
                self.notify(f"Killed {project}", severity="information")
                self._refresh_state()
            else:
                self.notify(f"Could not find process for {project}", severity="error")

        self.push_screen(
            ConfirmScreen(f"Kill session [bold]{project}[/bold]?"),
            on_confirm,
        )

    def action_help(self) -> None:
        self.notify(
            "[Enter/g] Go to session  [d] Kill  [t] Theme  [q] Quit",
            timeout=10,
        )
