"""Main Textual TUI application."""

import os

import yaml
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, DataTable

from flaude.constants import CONFIG_PATH, DEFAULT_THEME, utcnow
from flaude.state.manager import StateManager
from flaude.state.models import SessionStatus
from flaude.state.cleanup import cleanup_stale_sessions
from flaude.terminal.detect import detect_terminal
from flaude.terminal.launch import launch_session
from flaude.terminal.navigate import navigate_to_session
from flaude.tui.screens.input_dialog import InputDialog
from flaude.tui.screens.help_dialog import HelpDialog
from flaude.tui.screens.notification_settings import NotificationSettings
from flaude.tui.widgets.session_table import SessionTable
from flaude.tui.widgets.session_detail import SessionDetail
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
        Binding("g", "goto_session", "Go to Session"),
        Binding("n", "new_session", "New Claude Session"),
        Binding("l", "cycle_log_mode", "Log Mode"),
        Binding("s", "toggle_notifications", "Notifications"),
        Binding("S", "notification_settings", "Notification Settings", show=False),
        Binding("t", "change_theme", "Theme"),
        Binding("question_mark", "help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._mgr = StateManager()
        self._fallback_terminal = detect_terminal()
        self._config = _load_config()
        self.theme = self._config.get("theme", DEFAULT_THEME)
        self._alerted_turns: set[str] = set()

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

        selected_id = table.get_selected_session_id()

        # Update detail panel
        detail = self.query_one(SessionDetail)
        if selected_id and selected_id in active:
            detail.update_session(active[selected_id])
        else:
            detail.update_session(None)

        log = self.query_one(ActivityLog)
        log.set_session_filter(selected_id)
        # Pass transcript path for the selected session
        if selected_id and selected_id in active:
            log.set_transcript_path(active[selected_id].transcript_path)
        else:
            log.set_transcript_path(None)
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

        # Alert when a long turn finishes
        notif = self._config.get("notifications", {})
        if notif.get("enabled", True):
            threshold = notif.get("long_turn_minutes", 5) * 60
            for sid, state in active.items():
                if (
                    state.last_turn_duration > threshold
                    and state.turn_started_at is None
                    and sid not in self._alerted_turns
                ):
                    self._fire_alert(state)
                    self._alerted_turns.add(sid)
                # Reset when a new turn starts
                if state.turn_started_at is not None:
                    self._alerted_turns.discard(sid)

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

    def action_cycle_log_mode(self) -> None:
        log = self.query_one(ActivityLog)
        log.cycle_mode()
        self._config["log_mode"] = log.mode
        try:
            _save_config(self._config)
        except Exception:
            pass
        from flaude.tui.widgets.activity_log import MODE_LABELS

        self.notify(f"Log: {MODE_LABELS[log.mode]}")

    def _fire_alert(self, state) -> None:
        """Fire configured notification methods."""
        import subprocess
        from pathlib import Path

        notif = self._config.get("notifications", {})
        project = Path(state.cwd).name if state.cwd else state.session_id[:8]
        duration = _format_alert_duration(state.last_turn_duration)
        prompt_preview = (state.last_prompt or "")[:80].replace('"', '\\"')

        if notif.get("terminal_bell", True):
            self.bell()
        if notif.get("system_sound", False):
            subprocess.Popen(
                ["afplay", "/System/Library/Sounds/Glass.aiff"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        if notif.get("macos_alert", False):
            subprocess.Popen(
                [
                    "osascript",
                    "-e",
                    f'display notification "{prompt_preview}" '
                    f'with title "Flaude — {project}" subtitle "Finished in {duration}"',
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def action_toggle_notifications(self) -> None:
        notif = self._config.setdefault("notifications", {})
        enabled = not notif.get("enabled", True)
        notif["enabled"] = enabled
        try:
            _save_config(self._config)
        except Exception:
            pass
        if enabled:
            self.notify("Notifications: ON")
        else:
            self.notify("Notifications: OFF")
            self._alerted_turns.clear()

    def action_notification_settings(self) -> None:
        current = self._config.get(
            "notifications",
            {
                "enabled": True,
                "terminal_bell": True,
                "macos_alert": False,
                "system_sound": False,
                "long_turn_minutes": 5,
            },
        )

        def on_result(result: dict | None) -> None:
            if result is None:
                return
            self._config["notifications"] = result
            try:
                _save_config(self._config)
            except Exception:
                pass
            self._alerted_turns.clear()
            status = "ON" if result["enabled"] else "OFF"
            self.notify(f"Notifications: {status} ({result['long_turn_minutes']}min)")

        self.push_screen(NotificationSettings(current), on_result)

    def action_help(self) -> None:
        self.push_screen(HelpDialog())


def _format_alert_duration(seconds: float) -> str:
    mins = int(seconds // 60)
    if mins < 60:
        return f"{mins}m"
    return f"{mins // 60}h{mins % 60}m"
