"""Waiting sessions panel — shows which sessions need attention."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, ListView, ListItem

from flaude.state.models import SessionState, SessionStatus


class WaitingItem(ListItem):
    """A session that's waiting for user input."""

    def __init__(self, session_id: str, state: SessionState) -> None:
        super().__init__()
        self.session_id = session_id
        self._state = state

    def compose(self) -> ComposeResult:
        status = (
            "Permission"
            if self._state.status == SessionStatus.WAITING_PERMISSION
            else "Input"
        )
        tool_info = ""
        if self._state.last_tool:
            tool_info = (
                f" — {self._state.last_tool.name}: {self._state.last_tool.summary}"
            )
        yield Static(
            f"[bold][{self.session_id[:8]}][/bold] Waiting for {status}{tool_info}"
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
            in (SessionStatus.WAITING_PERMISSION, SessionStatus.WAITING_ANSWER)
        }

        no_perms = self.query_one("#no-permissions", Static)
        perm_list = self.query_one("#permission-list", ListView)

        if not waiting:
            no_perms.display = True
            perm_list.display = False
            self.border_title = "Waiting"
            return

        no_perms.display = False
        perm_list.display = True
        self.border_title = f"Waiting ({len(waiting)})"

        perm_list.clear()
        for sid, state in waiting.items():
            perm_list.append(WaitingItem(sid, state))
