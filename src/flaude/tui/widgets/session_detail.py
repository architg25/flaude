"""Session detail panel — shows info about the selected session."""

from pathlib import Path

from textual.widgets import Static

from flaude.constants import utcnow
from flaude.state.models import SessionState

_MODEL_LIMITS = {
    "claude-opus-4-6": 1_000_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5": 200_000,
}


class SessionDetail(Static):
    """Displays detailed info for the selected session."""

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)

    def update_session(self, state: SessionState | None) -> None:
        if state is None:
            self.update("[dim]Select a session to view details[/]")
            self.border_title = "Detail"
            return

        project = Path(state.cwd).name if state.cwd else "?"
        self.border_title = f"Detail — {project}"

        lines = []

        # Session info
        lines.append(f"[bold]Session[/]     {state.session_id}")
        lines.append(f"[bold]Status[/]      {state.status.value}")
        lines.append(f"[bold]Project[/]     {project}")
        lines.append(f"[bold]Directory[/]   {state.cwd}")
        lines.append(f"[bold]Terminal[/]    {state.terminal or '?'}")
        lines.append(f"[bold]Mode[/]        {state.permission_mode}")
        if state.model:
            lines.append(f"[bold]Model[/]       {state.model}")
        lines.append(f"[bold]Started[/]     {state.started_at.strftime('%H:%M')}")
        lines.append(f"[bold]Uptime[/]      {_format_uptime(state.started_at)}")
        if state.turn_started_at:
            turn_secs = int((utcnow() - state.turn_started_at).total_seconds())
            mins, secs = divmod(turn_secs, 60)
            lines.append(f"[bold]Turn[/]        {mins}m{secs:02d}s")
        if state.context_tokens > 0:
            ctx = state.context_tokens
            if ctx >= 1_000_000:
                ctx_str = f"{ctx / 1_000_000:.1f}M"
            elif ctx >= 1_000:
                ctx_str = f"{ctx // 1_000}K"
            else:
                ctx_str = str(ctx)
            limit = _MODEL_LIMITS.get(state.model or "", 200_000)
            if limit >= 1_000_000:
                limit_str = f"{limit // 1_000_000}M"
            else:
                limit_str = f"{limit // 1_000}K"
            lines.append(f"[bold]Context[/]     {ctx_str} / {limit_str}")

        # Last prompt
        if state.last_prompt:
            lines.append("")
            lines.append("[bold]Last Prompt[/]")
            lines.append(f"  [italic]{state.last_prompt}[/]")

        # Pending question
        pq = state.pending_question
        if pq:
            lines.append("")
            if "questions" in pq:
                lines.append("[bold]Pending Question[/]")
                for q in pq["questions"]:
                    lines.append(f"  [italic]{q.get('question', '')}[/]")
                    for opt in q.get("options", []):
                        label = opt.get("label", "")
                        desc = opt.get("description", "")
                        if desc:
                            lines.append(f"    - [bold]{label}[/]: {desc}")
                        else:
                            lines.append(f"    - [bold]{label}[/]")
            else:
                lines.append("[bold]Plan approval needed[/]")

        self.update("\n".join(lines))


def _format_uptime(started) -> str:
    delta = utcnow() - started
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h{minutes % 60}m"
    days = hours // 24
    return f"{days}d{hours % 24}h"
