"""Loop manager panel — shows scheduled tasks across all sessions."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from flaude.state.models import SessionState
from flaude.tools import trunc


class LoopPanel(ModalScreen[None]):
    """Modal panel showing loops grouped by session."""

    BINDINGS = [
        Binding("escape", "dismiss_panel", "Close"),
        Binding("L", "dismiss_panel", "Close", show=False),
    ]

    DEFAULT_CSS = """
    LoopPanel {
        align: center middle;
    }
    #loop-dialog {
        width: 72;
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
    #loop-content {
        height: auto;
        max-height: 60;
    }
    .loop-session-header {
        text-style: bold;
        color: $primary;
        margin-top: 1;
    }
    .loop-row {
        height: 1;
        padding-left: 2;
    }
    .loop-empty {
        color: $text-muted;
        text-align: center;
        margin-top: 1;
    }
    #loop-hint {
        color: $text-muted;
        text-align: center;
        margin-top: 1;
    }
    """

    def __init__(self, sessions: dict[str, SessionState]) -> None:
        super().__init__()
        self._sessions = sessions

    def compose(self) -> ComposeResult:
        with Vertical(id="loop-dialog"):
            yield Static("Loops", id="loop-title")
            with VerticalScroll(id="loop-content"):
                yield from self._build_content()
            yield Static(
                "[bold]L[/] or [bold]Esc[/] to close",
                id="loop-hint",
            )

    def _build_content(self) -> ComposeResult:
        sessions_with_loops = {sid: s for sid, s in self._sessions.items() if s.loops}
        sessions_without = len(self._sessions) - len(sessions_with_loops)

        if not sessions_with_loops:
            yield Static("No active loops", classes="loop-empty")
            return

        for sid, session in sessions_with_loops.items():
            project = _project_name(session)
            yield Static(
                f"[bold]{project}[/] ({sid[:8]})",
                classes="loop-session-header",
            )
            for loop in session.loops.values():
                marker = "\u21bb" if loop.recurring else "\u2460"
                cron = loop.cron_expr or loop.human_schedule
                prompt = trunc(loop.prompt, 40)
                yield Static(
                    f"  {loop.task_id}  {cron:<14} {marker} {prompt}",
                    classes="loop-row",
                )

        if sessions_without:
            noun = "session" if sessions_without == 1 else "sessions"
            yield Static(
                f"[dim]No loops: {sessions_without} other {noun}[/]",
                classes="loop-empty",
            )

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
