"""Pending permissions widget — approve/deny tool permissions from the dashboard."""

from datetime import datetime

from flaude.constants import utcnow

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, ListView, ListItem, Label

from flaude.state.manager import StateManager
from flaude.state.models import SessionState, PendingPermission


class PermissionItem(ListItem):
    """A single pending permission entry."""

    def __init__(self, session_id: str, permission: PendingPermission) -> None:
        super().__init__()
        self.session_id = session_id
        self.permission = permission

    def compose(self) -> ComposeResult:
        p = self.permission
        remaining = _format_remaining(p.timeout_at)
        tool_summary = _summarize_tool_input(p.tool_name, p.tool_input)

        yield Static(
            f"[bold][{self.session_id[:6]}][/bold] {p.tool_name}: {tool_summary}"
        )
        parts = []
        if p.rule_matched:
            parts.append(f"Rule: {p.rule_matched}")
        parts.append(f"⏱ {remaining}")
        yield Static("  ".join(parts), classes="dim")


class PermissionPanel(Vertical):
    """Panel showing all pending permissions with approve/deny actions."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._permissions: list[tuple[str, PendingPermission]] = []

    def compose(self) -> ComposeResult:
        yield Static("No pending permissions", id="no-permissions")
        yield ListView(id="permission-list")

    def on_mount(self) -> None:
        self.border_title = "Pending Permissions"
        self.query_one("#permission-list", ListView).display = False

    def update_permissions(self, sessions: dict[str, SessionState]) -> None:
        """Rebuild the permission list from current state."""
        self._permissions = []
        for sid, state in sessions.items():
            for perm in state.pending_permissions:
                self._permissions.append((sid, perm))

        # Sort by timeout (most urgent first)
        self._permissions.sort(key=lambda x: x[1].timeout_at)

        no_perms = self.query_one("#no-permissions", Static)
        perm_list = self.query_one("#permission-list", ListView)

        if not self._permissions:
            no_perms.display = True
            perm_list.display = False
            self.border_title = "Pending Permissions"
            return

        no_perms.display = False
        perm_list.display = True
        self.border_title = f"Pending Permissions ({len(self._permissions)})"

        perm_list.clear()
        for sid, perm in self._permissions:
            perm_list.append(PermissionItem(sid, perm))

    def get_selected_permission(self) -> tuple[str, PendingPermission] | None:
        """Return (session_id, permission) of the highlighted item."""
        perm_list = self.query_one("#permission-list", ListView)
        if perm_list.index is not None and self._permissions:
            idx = perm_list.index
            if 0 <= idx < len(self._permissions):
                return self._permissions[idx]
        # Fall back to first if any exist
        if self._permissions:
            return self._permissions[0]
        return None

    def approve_selected(self, mgr: StateManager) -> bool:
        """Approve the selected permission. Returns True if approved."""
        selected = self.get_selected_permission()
        if not selected:
            return False
        sid, perm = selected
        mgr.write_decision(sid, perm.request_id, "allow")
        return True

    def deny_selected(self, mgr: StateManager) -> bool:
        """Deny the selected permission. Returns True if denied."""
        selected = self.get_selected_permission()
        if not selected:
            return False
        sid, perm = selected
        mgr.write_decision(sid, perm.request_id, "deny")
        return True

    def approve_all(self, mgr: StateManager) -> int:
        """Approve all pending permissions. Returns count approved."""
        count = 0
        for sid, perm in self._permissions:
            mgr.write_decision(sid, perm.request_id, "allow")
            count += 1
        return count


def _format_remaining(timeout_at: datetime) -> str:
    remaining = (timeout_at - utcnow()).total_seconds()
    if remaining <= 0:
        return "expired"
    minutes = int(remaining // 60)
    seconds = int(remaining % 60)
    return f"{minutes}:{seconds:02d}"


def _summarize_tool_input(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return f'"{cmd[:60]}"' if cmd else ""
    if tool_name in ("Edit", "Write", "Read", "MultiEdit"):
        path = tool_input.get("file_path", "")
        return path.rsplit("/", 1)[-1] if path else ""
    if tool_name == "Grep":
        return tool_input.get("pattern", "")[:40]
    if tool_name == "Glob":
        return tool_input.get("pattern", "")
    if tool_name == "Task":
        return tool_input.get("prompt", "")[:40]
    if tool_name == "WebFetch":
        return tool_input.get("url", "")[:40]
    return ""
