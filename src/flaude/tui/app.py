"""Main Textual TUI application."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, DataTable

from flaude.config import load_config, save_config, migrate_notifications_config
from flaude.constants import (
    DEFAULT_THEME,
    SOFT_HIDE_TIMEOUT,
    TUI_REFRESH_INTERVAL,
    utcnow,
)
from flaude.state.manager import StateManager
from flaude.state.models import SessionState, SessionStatus, WAITING_STATUSES
from flaude.state.cleanup import cleanup_stale_sessions, correct_stale_waiting
from flaude.state.scanner import scan_preexisting_sessions
from flaude.terminal.detect import detect_terminal
from flaude.terminal.launch import launch_session
from flaude.terminal.inject import send_text_to_session
from flaude.terminal.navigate import navigate_to_session
from flaude.terminal.tmux import (
    build_tmux_attach_command,
    build_tmux_attach_shell_command,
    get_tmux_client_tty,
    get_tmux_prefix,
    is_flaude_in_tmux,
    is_tmux_available,
    launch_tmux_session,
    navigate_tmux_session,
    send_text_tmux,
)
from flaude.tui.notifications import NotificationManager
from flaude.tui.screens.confirm_dialog import ConfirmDialog
from flaude.tui.screens.input_dialog import InputDialog
from flaude.tui.screens.prompt_dialog import PromptDialog
from flaude.tui.screens.help_dialog import HelpDialog
from flaude.tui.screens.settings_panel import SettingsPanel
from flaude.tui.screens.loop_panel import LoopPanel
from flaude.tui.widgets.session_table import (
    SessionTable,
    REPO_HEADER_PREFIX,
    GROUP_HEADER_PREFIX,
)
from flaude.tui.widgets.session_detail import SessionDetail
from flaude.tui.widgets.permission_panel import PermissionPanel
from flaude.tui.widgets.activity_log import ActivityLog


class FlaudeApp(App):
    """Claude Code session manager dashboard."""

    CSS_PATH = "app.tcss"
    TITLE = "flaude"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("g", "goto_session", "Goto"),
        Binding("n", "new_session", "New"),
        Binding("p", "send_prompt", "Prompt"),
        Binding("d", "exit_session", "Exit"),
        Binding("l", "cycle_log_mode", "Log"),
        Binding("s", "toggle_notifications", "Notif"),
        Binding("S", "settings", "Settings"),
        Binding("G", "assign_group", "Assign Group", show=False),
        Binding("h", "toggle_hidden", "Hidden"),
        Binding("t", "change_theme", "Theme", show=False),
        Binding("question_mark", "help", "Help"),
        Binding("L", "show_loops", "Loops"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._mgr = StateManager()
        self._fallback_terminal = detect_terminal()
        self._flaude_in_tmux = is_flaude_in_tmux()
        self._config = load_config()
        self._config = migrate_notifications_config(self._config)
        save_config(self._config)
        self.theme = self._config.get("theme", DEFAULT_THEME)
        self._notifier = NotificationManager(bell=self.bell)
        self._active: dict[str, SessionState] = {}
        self._selected_id: str | None = None
        self._show_hidden = False

    def compose(self) -> ComposeResult:
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
            if s.status != SessionStatus.ENDED and (s.terminal is not None or s.is_tmux)
        }
        correct_stale_waiting(self._mgr, active)
        self._active = active

        # Soft-hide: IDLE and NEW sessions past the threshold get hidden
        # Env var FLAUDE_SOFT_HIDE_TIMEOUT (seconds) overrides config if set
        now = utcnow()
        if SOFT_HIDE_TIMEOUT is not None:
            hide_seconds = SOFT_HIDE_TIMEOUT
        else:
            hide_seconds = self._config.get("soft_hide_minutes", 30) * 60

        if self._show_hidden:
            visible = active
            hidden_count = 0
        else:
            visible = {}
            hidden_count = 0
            for sid, s in active.items():
                idle_age = (now - s.last_event_at).total_seconds()
                if (
                    s.status in (SessionStatus.IDLE, SessionStatus.NEW)
                    and idle_age >= hide_seconds
                ):
                    hidden_count += 1
                else:
                    visible[sid] = s

        table = self.query_one(SessionTable)
        any_named = any(s.custom_title for s in active.values())
        table.update_sessions(
            visible,
            hidden_count=hidden_count,
            any_named=any_named,
            group_names=self._config.get("group_names"),
            auto_group=self._config.get("auto_group", True),
            session_groups=self._config.get("session_groups"),
        )
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
        group_names = self._config.get("group_names")
        session_groups = self._config.get("session_groups")
        if selected_id and selected_id in active:
            detail.update_session(
                active[selected_id],
                group_names=group_names,
                session_groups=session_groups,
            )
        else:
            detail.update_session(None)

        log = self.query_one(ActivityLog)
        log.set_session_filter(selected_id)
        if selected_id and selected_id in active:
            log.set_session_id(selected_id)
            log.set_transcript_path(active[selected_id].transcript_path)
        else:
            log.set_session_id(None)
            log.set_transcript_path(None)
        log.refresh_log()

    def _schedule_cleanup(self) -> None:
        self.run_worker(self._cleanup, thread=True)

    def _cleanup(self) -> None:
        cleanup_stale_sessions(self._mgr)

    def _update_config_dict(self, key: str, data: dict) -> None:
        """Save a config dict, removing the key entirely if empty."""
        if data:
            self._config[key] = data
        else:
            self._config.pop(key, None)
        save_config(self._config)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Trigger immediate detail+log refresh when cursor moves to a new session."""
        key = str(event.row_key.value) if event.row_key else ""
        if key.startswith(REPO_HEADER_PREFIX) or key.startswith(GROUP_HEADER_PREFIX):
            return
        if key and key != self._selected_id:
            self._selected_id = key
            self._refresh_log()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter: navigate to session, or rename group if on a header."""
        key = str(event.row_key.value) if event.row_key else ""
        if key.startswith(REPO_HEADER_PREFIX):
            self._rename_repo_group(key.removeprefix(REPO_HEADER_PREFIX))
        elif key.startswith(GROUP_HEADER_PREFIX):
            self._rename_manual_group(key.removeprefix(GROUP_HEADER_PREFIX))
        else:
            self.action_goto_session()

    def _rename_repo_group(self, repo_root: str) -> None:
        """Rename an auto-detected repo group."""
        group_names = self._config.get("group_names", {})
        current = group_names.get(repo_root) or Path(repo_root).name
        auto_name = Path(repo_root).name

        def on_result(name: str | None) -> None:
            if name is None:
                return
            name = name.strip()
            groups = self._config.setdefault("group_names", {})
            if not name or name == auto_name:
                groups.pop(repo_root, None)
            else:
                groups[repo_root] = name
            self._update_config_dict("group_names", groups)
            self._refresh_sessions()

        self.push_screen(
            InputDialog("Group name:", current, autocomplete=False), on_result
        )

    def _rename_manual_group(self, old_name: str) -> None:
        """Rename a manual group — updates all sessions assigned to it."""

        def on_result(name: str | None) -> None:
            if name is None:
                return
            name = name.strip()
            sg = self._config.get("session_groups", {})
            if not name:
                sg = {sid: g for sid, g in sg.items() if g != old_name}
            elif name != old_name:
                sg = {sid: (name if g == old_name else g) for sid, g in sg.items()}
            self._update_config_dict("session_groups", sg)
            self._refresh_sessions()

        self.push_screen(
            InputDialog("Group name:", old_name, autocomplete=False), on_result
        )

    def action_assign_group(self) -> None:
        """Assign the selected session to a manual group."""
        table = self.query_one(SessionTable)
        session_id = table.get_selected_session_id()
        if not session_id:
            self.notify("Select a session to assign", severity="warning")
            return

        sg = self._config.get("session_groups", {})
        current = sg.get(session_id, "")

        def on_result(name: str | None) -> None:
            if name is None:
                return
            name = name.strip()
            groups = self._config.setdefault("session_groups", {})
            if name:
                groups[session_id] = name
            else:
                groups.pop(session_id, None)
            self._update_config_dict("session_groups", groups)
            self._refresh_sessions()

        self.push_screen(
            InputDialog("Group name:", current, autocomplete=False), on_result
        )

    def action_goto_session(self) -> None:
        table = self.query_one(SessionTable)
        session_id = table.get_selected_session_id()
        if not session_id:
            self.notify("No session selected", severity="warning")
            return
        self._navigate_to(session_id)

    def _navigate_to(self, session_id: str) -> None:
        """Navigate to a session by ID."""
        state = self._mgr.load_session(session_id)
        if not state:
            self.notify("Session not found", severity="error")
            return

        if state.is_tmux and state.tmux_pane:
            self._goto_tmux_session(state)
        else:
            terminal = state.terminal or self._fallback_terminal
            if navigate_to_session(terminal, state.cwd, tty=state.tty):
                self.notify(f"Switched to {session_id[:8]}")
            else:
                self.notify(
                    f"Could not switch. Resume with: claude --resume {session_id}",
                    severity="warning",
                    timeout=10,
                )

    def _goto_tmux_session(self, state: SessionState) -> None:
        """Navigate to a tmux-based session, respecting config."""
        pane = state.tmux_pane
        sid_short = state.session_id[:8]
        nav_terminal = state.parent_terminal or self._fallback_terminal
        open_mode = self._config.get("tmux_open_mode", "inline")

        if open_mode == "inline":
            if self._flaude_in_tmux:
                # Same tmux server — just switch windows
                if navigate_tmux_session(pane):
                    self.notify(f"Switched to {sid_short}")
                else:
                    self.notify("Could not switch tmux pane", severity="error")
            else:
                # Suspend flaude TUI, attach tmux
                prefix = get_tmux_prefix()
                attach_argv = build_tmux_attach_command(pane)
                self.notify(
                    f"Attaching. Press {prefix} D to return.",
                    timeout=3,
                )

                import subprocess
                import time

                time.sleep(0.3)  # let notification render
                with self.suspend():
                    subprocess.run(attach_argv)
        else:
            # new_tab mode: try to find existing iTerm2 tab first
            if not self._flaude_in_tmux and nav_terminal == "iTerm2":
                client_tty = get_tmux_client_tty(pane)
                if client_tty and navigate_to_session(
                    "iTerm2", state.cwd, tty=client_tty
                ):
                    self.notify(f"Switched to {sid_short}")
                    return

            # Open a new tab with tmux attach
            attach_cmd = build_tmux_attach_shell_command(pane)
            if launch_session(nav_terminal, state.cwd, command=attach_cmd):
                self.notify(f"Opened {sid_short} in new tab")
            else:
                self.notify(
                    f"Could not open tab ({nav_terminal or 'unknown'})",
                    severity="error",
                )

    def action_new_session(self) -> None:
        table = self.query_one(SessionTable)
        session_id = table.get_selected_session_id()
        default_cwd = "~"
        if session_id:
            state = self._mgr.load_session(session_id)
            if state and state.cwd:
                default_cwd = state.cwd

        use_tmux = self._config.get("launch_backend") == "tmux"

        def on_result(path: str | None) -> None:
            if not path:
                return
            basename = path.rsplit("/", 1)[-1]
            if use_tmux:
                if not is_tmux_available():
                    self.notify(
                        "tmux not found. Install: brew install tmux",
                        severity="error",
                    )
                    return
                if launch_tmux_session(path):
                    self.notify(f"Launched claude in {basename} (tmux)")
                else:
                    self.notify("Could not create tmux session", severity="error")
            else:
                terminal = self._fallback_terminal
                if launch_session(terminal, path):
                    self.notify(f"Launched claude in {basename}")
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

        use_tmux = state.is_tmux and state.tmux_pane
        if not use_tmux:
            if state.terminal != "iTerm2":
                self.notify("Only iTerm2 or tmux supported", severity="warning")
                return
            if not state.tty:
                self.notify("No tty for session", severity="warning")
                return

        project = state.cwd.rsplit("/", 1)[-1] if state.cwd else session_id[:8]
        tty = state.tty
        tmux_pane = state.tmux_pane

        def on_result(text: str | None) -> None:
            if not text:
                return
            if use_tmux:
                ok = send_text_tmux(tmux_pane, text)
            else:
                ok = send_text_to_session(tty, text)
            if ok:
                self.notify(f"Sent to {project}")
            else:
                self.notify("Failed to send prompt", severity="error")

        self.push_screen(PromptDialog(f"Prompt ({project}):"), on_result)

    def action_exit_session(self) -> None:
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

        use_tmux = state.is_tmux and state.tmux_pane
        if not use_tmux:
            if state.terminal != "iTerm2":
                self.notify("Only iTerm2 or tmux supported", severity="warning")
                return
            if not state.tty:
                self.notify("No tty for session", severity="warning")
                return

        project = state.cwd.rsplit("/", 1)[-1] if state.cwd else session_id[:8]
        tty = state.tty
        tmux_pane = state.tmux_pane

        def on_result(confirmed: bool) -> None:
            if not confirmed:
                return
            if use_tmux:
                ok = send_text_tmux(tmux_pane, "/exit")
            else:
                ok = send_text_to_session(tty, "/exit")
            if ok:
                self.notify(f"Exiting {project}")
            else:
                self.notify("Failed to send /exit", severity="error")

        self.push_screen(
            ConfirmDialog(f"Exit session [bold]{project}[/] ({session_id[:8]})?"),
            on_result,
        )

    def action_toggle_hidden(self) -> None:
        self._show_hidden = not self._show_hidden
        self._refresh_sessions()
        label = "Showing all sessions" if self._show_hidden else "Hiding stale sessions"
        self.notify(label)

    def action_cycle_log_mode(self) -> None:
        log = self.query_one(ActivityLog)
        log.cycle_mode()
        self._config["log_mode"] = log.mode
        save_config(self._config)
        from flaude.tui.widgets.activity_log import MODE_LABELS

        self.notify(f"Log: {MODE_LABELS[log.mode]}")

    # ------------------------------------------------------------------
    # Settings & notifications
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

    def action_settings(self) -> None:
        self._config = migrate_notifications_config(self._config)

        def on_result(result: dict | None) -> None:
            if result is None:
                return
            self._config = result
            save_config(self._config)
            self._sync_notifier()
            self.notify("Settings saved")
            # One-time notice when user first enables tmux backend
            if self._config.get("launch_backend") == "tmux" and not self._config.get(
                "tmux_notice_seen"
            ):
                self._config["tmux_notice_seen"] = True
                save_config(self._config)
                self.notify(
                    "tmux support is new and may have rough edges — "
                    "please report any issues in #flaude, thanks!",
                    severity="warning",
                    timeout=10,
                )

        self.push_screen(SettingsPanel(self._config), on_result)

    def action_help(self) -> None:
        self.push_screen(HelpDialog())

    def _send_text_to(self, session_id: str, text: str) -> bool:
        """Send text to a session. Returns True on success."""
        state = self._mgr.load_session(session_id)
        if not state:
            return False
        if state.is_tmux and state.tmux_pane:
            return send_text_tmux(state.tmux_pane, text)
        if state.terminal == "iTerm2" and state.tty:
            return send_text_to_session(state.tty, text)
        return False

    def action_show_loops(self) -> None:
        def on_result(session_id: str | None) -> None:
            if session_id:
                self._navigate_to(session_id)

        self.push_screen(
            LoopPanel(lambda: self._active, self._send_text_to),
            on_result,
        )
