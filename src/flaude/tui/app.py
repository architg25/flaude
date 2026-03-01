"""Main Textual TUI application."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, DataTable

from flaude.config import load_config, save_config, migrate_notifications_config
from flaude.constants import DEFAULT_THEME, TUI_REFRESH_INTERVAL, utcnow
from flaude.state.manager import StateManager
from flaude.state.models import SessionState, SessionStatus, WAITING_STATUSES
from flaude.state.cleanup import cleanup_stale_sessions, correct_stale_waiting
from flaude.state.scanner import scan_preexisting_sessions
from flaude.terminal.detect import detect_terminal
from flaude.terminal.launch import launch_session
from flaude.terminal.inject import send_text_to_session
from flaude.terminal.navigate import navigate_to_session
from flaude.tui.notifications import NotificationManager
from flaude.tui.screens.input_dialog import InputDialog
from flaude.tui.screens.prompt_dialog import PromptDialog
from flaude.tui.screens.help_dialog import HelpDialog
from flaude.tui.screens.notification_settings import NotificationSettings
from flaude.tui.widgets.session_table import SessionTable
from flaude.tui.widgets.session_detail import SessionDetail
from flaude.tui.widgets.permission_panel import PermissionPanel
from flaude.tui.widgets.activity_log import ActivityLog


class FlaudeApp(App):
    """Claude Code session manager dashboard."""

    CSS_PATH = "app.tcss"
    TITLE = "🤖 Flaude"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("g", "goto_session", "Go to Session"),
        Binding("n", "new_session", "New Claude Session"),
        Binding("p", "send_prompt", "Send Prompt"),
        Binding("l", "cycle_log_mode", "Log Mode"),
        Binding(
            "s", "toggle_notifications", "Notif Toggle/Settings", key_display="s/S"
        ),
        Binding("S", "notification_settings", "Notification Settings", show=False),
        Binding("t", "change_theme", "Theme"),
        Binding("question_mark", "help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._mgr = StateManager()
        self._fallback_terminal = detect_terminal()
        self._config = load_config()
        self._config = migrate_notifications_config(self._config)
        save_config(self._config)
        self.theme = self._config.get("theme", DEFAULT_THEME)
        self._notifier = NotificationManager(bell=self.bell)
        self._active: dict[str, SessionState] = {}
        self._selected_id: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-split"):
            with Vertical(id="left-pane"):
                yield SessionTable(id="session-table")
                yield PermissionPanel(id="permission-panel")
                yield ActivityLog(
                    initial_mode=self._config.get("log_mode", "tools"),
                    id="activity-log",
                )
            yield SessionDetail(id="session-detail")
        yield Footer()

    def on_mount(self) -> None:
        scan_preexisting_sessions(self._mgr)
        self._sync_notifier()
        self.set_interval(TUI_REFRESH_INTERVAL, self._refresh_sessions)
        self.set_interval(TUI_REFRESH_INTERVAL * 2, self._refresh_log)
        self.set_interval(30.0, self._schedule_cleanup)
        self._refresh_sessions()
        self._refresh_log()
        self.run_worker(self._check_for_update, thread=True)

    def _check_for_update(self) -> None:
        from flaude.version_check import check_for_update

        result = check_for_update(self._config)
        if result:
            save_config(self._config)
            current, remote = result
            self.notify(
                f"Update available ({current} \u2192 {remote}). Run: flaude update",
                severity="information",
                timeout=10,
            )

    def watch_theme(self, theme: str) -> None:
        """Save theme selection whenever it changes."""
        self._config["theme"] = theme
        save_config(self._config)

    def _refresh_sessions(self) -> None:
        """Fast path: state files → table + permission panel + title."""
        sessions = self._mgr.load_all_sessions()
        active = {
            sid: s
            for sid, s in sessions.items()
            if s.status != SessionStatus.ENDED and s.terminal is not None
        }
        correct_stale_waiting(self._mgr, active)
        self._active = active

        table = self.query_one(SessionTable)
        table.update_sessions(active)
        self.query_one(PermissionPanel).update_permissions(active)
        self._selected_id = table.get_selected_session_id()

        waiting = sum(1 for s in active.values() if s.status in WAITING_STATUSES)
        notif = self._config.get("notifications", {})
        notif_icon = "🔔" if notif.get("enabled", False) else "🔕"
        if waiting:
            self.title = (
                f"Flaude ({len(active)} sessions, {waiting} waiting) {notif_icon}"
            )
        else:
            self.title = f"Flaude ({len(active)} sessions) {notif_icon}"

        self._notifier.check(active, notif)

    def _refresh_log(self) -> None:
        """Slow path: session detail + activity log."""
        active = self._active
        selected_id = self._selected_id

        detail = self.query_one(SessionDetail)
        if selected_id and selected_id in active:
            detail.update_session(active[selected_id])
        else:
            detail.update_session(None)

        log = self.query_one(ActivityLog)
        log.set_session_filter(selected_id)
        if selected_id and selected_id in active:
            log.set_transcript_path(active[selected_id].transcript_path)
        else:
            log.set_transcript_path(None)
        log.refresh_log()

    def _schedule_cleanup(self) -> None:
        self.run_worker(self._cleanup, thread=True)

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

        if navigate_to_session(terminal, state.cwd, tty=state.tty):
            self.notify(f"Switched to {session_id[:8]}")
        else:
            self.notify(
                f"Could not switch. Resume with: claude --resume {session_id}",
                severity="warning",
                timeout=10,
            )

    def action_new_session(self) -> None:
        table = self.query_one(SessionTable)
        session_id = table.get_selected_session_id()
        default_cwd = "~"
        if session_id:
            state = self._mgr.load_session(session_id)
            if state and state.cwd:
                default_cwd = state.cwd

        def on_result(path: str | None) -> None:
            if not path:
                return
            terminal = self._fallback_terminal
            if launch_session(terminal, path):
                self.notify(f"Launched claude in {path.rsplit('/', 1)[-1]}")
            else:
                self.notify(
                    f"Could not open terminal ({terminal or 'unknown'})",
                    severity="error",
                )

        self.push_screen(InputDialog("New session directory:", default_cwd), on_result)

    def action_send_prompt(self) -> None:
        table = self.query_one(SessionTable)
        session_id = table.get_selected_session_id()
        if not session_id:
            self.notify("No session selected", severity="warning")
            return

        state = self._mgr.load_session(session_id)
        if not state:
            self.notify("Session not found", severity="error")
            return

        if state.status not in (SessionStatus.IDLE, SessionStatus.NEW):
            self.notify("Session is busy", severity="warning")
            return

        if state.terminal != "iTerm2":
            self.notify("Only iTerm2 supported", severity="warning")
            return

        if not state.tty:
            self.notify("No tty for session", severity="warning")
            return

        project = state.cwd.rsplit("/", 1)[-1] if state.cwd else session_id[:8]
        tty = state.tty

        def on_result(text: str | None) -> None:
            if not text:
                return
            if send_text_to_session(tty, text):
                self.notify(f"Sent to {project}")
            else:
                self.notify("Failed to send prompt", severity="error")

        self.push_screen(PromptDialog(f"Prompt ({project}):"), on_result)

    def action_cycle_log_mode(self) -> None:
        log = self.query_one(ActivityLog)
        log.cycle_mode()
        self._config["log_mode"] = log.mode
        save_config(self._config)
        from flaude.tui.widgets.activity_log import MODE_LABELS

        self.notify(f"Log: {MODE_LABELS[log.mode]}")

    # ------------------------------------------------------------------
    # Notification actions
    # ------------------------------------------------------------------

    def _sync_notifier(self) -> None:
        """Seed or clear the notifier based on current config."""
        notif = self._config.get("notifications", {})
        if notif.get("enabled", False):
            active = {
                sid: s
                for sid, s in self._mgr.load_all_sessions().items()
                if s.status != SessionStatus.ENDED
            }
            self._notifier.seed(active, notif)
        else:
            self._notifier.clear()

    def action_toggle_notifications(self) -> None:
        notif = self._config.setdefault("notifications", {})
        enabled = not notif.get("enabled", False)
        notif["enabled"] = enabled
        save_config(self._config)
        self._sync_notifier()
        self.notify(f"Notifications: {'ON' if enabled else 'OFF'}")

    def action_notification_settings(self) -> None:
        current = self._config.get("notifications", {})
        current = migrate_notifications_config({"notifications": current})[
            "notifications"
        ]

        def on_result(result: dict | None) -> None:
            if result is None:
                return
            self._config["notifications"] = result
            save_config(self._config)
            self._sync_notifier()
            status = "ON" if result["enabled"] else "OFF"
            self.notify(f"Notifications: {status}")

        self.push_screen(NotificationSettings(current), on_result)

    def action_help(self) -> None:
        self.push_screen(HelpDialog())
