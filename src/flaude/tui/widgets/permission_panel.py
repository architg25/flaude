"""Waiting sessions panel — shows which sessions need attention."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, ListView, ListItem

from flaude.state.models import SessionState, SessionStatus, STATUS_INFO


class WaitingItem(ListItem):
    """A session that's waiting for user input."""

    def __init__(self, session_id: str, state: SessionState) -> None:
        super().__init__()
        self.session_id = session_id
        self._state = state

    def compose(self) -> ComposeResult:
        project = Path(self._state.cwd).name if self._state.cwd else "?"
        info = STATUS_INFO[self._state.status]
        label = f"{info.indicator} {info.label}"

        tool = self._state.last_tool.name if self._state.last_tool else ""
        tool_str = f" ({tool})" if tool else ""
        yield Static(
            f" [bold][{self.session_id[:8]}][/bold] {project} [dim]─[/] {label}{tool_str}"
        )


class PermissionPanel(Vertical):
    """Panel showing sessions that need user attention."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Static("No sessions waiting", id="no-permissions")
        yield ListView(id="permission-list")

    def on_mount(self) -> None:
        self.border_title = "Waiting"
        self.query_one("#permission-list", ListView).display = False

    def update_permissions(self, sessions: dict[str, SessionState]) -> None:
        waiting = {
            sid: s
            for sid, s in sessions.items()
            if s.status
            in (
                SessionStatus.WAITING_PERMISSION,
                SessionStatus.WAITING_ANSWER,
                SessionStatus.PLAN,
            )
        }

        no_perms = self.query_one("#no-permissions", Static)
        perm_list = self.query_one("#permission-list", ListView)

        if not waiting:
            if getattr(self, "_last_waiting_ids", None) is not None:
                self._last_waiting_ids = None
                no_perms.display = True
                perm_list.display = False
                self.border_title = "Waiting"
                self.remove_class("has-waiting")
            return

        waiting_ids = frozenset(waiting.keys())
        if waiting_ids == getattr(self, "_last_waiting_ids", None):
            return
        self._last_waiting_ids = waiting_ids

        no_perms.display = False
        perm_list.display = True
        self.border_title = f"⏳ Waiting ({len(waiting)})"
        self.add_class("has-waiting")

        perm_list.clear()
        sorted_waiting = sorted(
            waiting.items(),
            key=lambda item: (
                STATUS_INFO[item[1].status].sort_priority,
                item[1].started_at,
            ),
        )
        for sid, state in sorted_waiting:
            perm_list.append(WaitingItem(sid, state))
