"""Session detail panel — shows info about the selected session."""

from pathlib import Path

from textual.widgets import Static

from flaude.constants import utcnow
from flaude.state.models import SessionState, SessionStatus

_MODEL_LIMITS = {
    "claude-opus-4-6": 1_000_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5": 200_000,
}

_STATUS_STYLES = {
    SessionStatus.NEW: "blue bold",
    SessionStatus.WORKING: "green bold",
    SessionStatus.IDLE: "dim",
    SessionStatus.WAITING_PERMISSION: "yellow bold",
    SessionStatus.WAITING_ANSWER: "cyan bold",
    SessionStatus.ERROR: "red bold",
    SessionStatus.ENDED: "dim",
}


class SessionDetail(Static):
    """Displays detailed info for the selected session."""

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)

    def update_session(self, state: SessionState | None) -> None:
        if state is None:
            self.update("[dim italic]Select a session to view details[/]")
            self.border_title = "Detail"
            return

        project = Path(state.cwd).name if state.cwd else "?"
        self.border_title = f"Detail -- {project}"

        lines: list[str] = []

        # ── Session ──
        lines.append("[dim bold]SESSION[/]")
        lines.append(f"  {state.session_id}")
        lines.append(f"  {state.cwd}")

        lines.append("")

        # ── Status ──
        style = _STATUS_STYLES.get(state.status, "dim")
        lines.append("[dim bold]STATUS[/]")
        lines.append(f"  [{style}]{state.status.value}[/]")
        if state.model:
            lines.append(f"  [dim]Model[/]  {state.model}")
        lines.append(f"  [dim]Mode[/]   {state.permission_mode}")
        lines.append(f"  [dim]Term[/]   {state.terminal or '?'}")

        lines.append("")

        # ── Timing ──
        lines.append("[dim bold]TIMING[/]")
        lines.append(f"  [dim]Up[/]     {_format_uptime(state.started_at)}")
        lines.append(f"  [dim]Since[/]  {state.started_at.strftime('%H:%M')}")
        if state.turn_started_at:
            turn_secs = int((utcnow() - state.turn_started_at).total_seconds())
            mins, secs = divmod(turn_secs, 60)
            lines.append(f"  [dim]Turn[/]   {mins}m{secs:02d}s")

        # ── Context ──
        if state.context_tokens > 0:
            lines.append("")
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
            ratio = state.context_tokens / limit if limit else 0
            if ratio > 0.8:
                bar_style = "red bold"
            elif ratio > 0.5:
                bar_style = "yellow"
            else:
                bar_style = "green"
            lines.append("[dim bold]CONTEXT[/]")
            lines.append(f"  [{bar_style}]{ctx_str}[/] / {limit_str}")

        # ── Last Prompt ──
        if state.last_prompt:
            lines.append("")
            lines.append("[dim bold]LAST PROMPT[/]")
            lines.append(f"  [italic]{state.last_prompt}[/]")

        # ── Pending Question ──
        pq = state.pending_question
        if pq:
            lines.append("")
            if "questions" in pq:
                lines.append("[yellow bold]PENDING QUESTION[/]")
                for q in pq["questions"]:
                    lines.append(f"  [italic]{q.get('question', '')}[/]")
                    for opt in q.get("options", []):
                        label = opt.get("label", "")
                        desc = opt.get("description", "")
                        if desc:
                            lines.append(f"    [dim]-[/] [bold]{label}[/]: {desc}")
                        else:
                            lines.append(f"    [dim]-[/] [bold]{label}[/]")
            else:
                lines.append("[yellow bold]PLAN APPROVAL NEEDED[/]")

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
