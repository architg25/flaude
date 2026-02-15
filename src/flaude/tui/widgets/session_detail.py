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
    SessionStatus.NEW: "$accent bold",
    SessionStatus.WORKING: "$success bold",
    SessionStatus.IDLE: "$text-muted",
    SessionStatus.WAITING_PERMISSION: "$warning bold",
    SessionStatus.WAITING_ANSWER: "$accent bold",
    SessionStatus.ERROR: "$error bold",
    SessionStatus.ENDED: "$text-muted",
}

_STATUS_INDICATORS = {
    SessionStatus.NEW: "◆",
    SessionStatus.WORKING: "▶",
    SessionStatus.IDLE: "●",
    SessionStatus.WAITING_PERMISSION: "⏳",
    SessionStatus.WAITING_ANSWER: "❓",
    SessionStatus.ERROR: "✖",
    SessionStatus.ENDED: "■",
}


def _section_header(title: str, width: int = 30, style: str = "bold") -> str:
    """Draw: ╶─── TITLE ───────────╴"""
    padding = width - len(title) - 2
    left = max(padding // 2, 1)
    right = max(padding - left, 1)
    return f"[{style}]╶{'─' * left} {title} {'─' * right}╴[/]"


def _kv(label: str, value: str, label_width: int = 7) -> str:
    """Render: Label   │ value"""
    return f"  [dim]{label:<{label_width}}[/] [dim]│[/] {value}"


def _context_bar(tokens: int, limit: int, width: int = 20) -> str:
    """Render: ████████░░░░░░░ 269K/1M"""
    ratio = min(tokens / limit, 1.0) if limit else 0
    filled = int(ratio * width)
    empty = width - filled

    if ratio > 0.8:
        bar_style = "$error"
    elif ratio > 0.5:
        bar_style = "$warning"
    else:
        bar_style = "$success"

    if tokens >= 1_000_000:
        ctx_str = f"{tokens / 1_000_000:.1f}M"
    elif tokens >= 1_000:
        ctx_str = f"{tokens // 1_000}K"
    else:
        ctx_str = str(tokens)
    if limit >= 1_000_000:
        limit_str = f"{limit // 1_000_000}M"
    else:
        limit_str = f"{limit // 1_000}K"

    bar = f"[{bar_style}]{'█' * filled}[/][dim]{'░' * empty}[/]"
    return f"  {bar} [{bar_style}]{ctx_str}[/][dim]/{limit_str}[/]"


class SessionDetail(Static):
    """Displays detailed info for the selected session."""

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)

    def update_session(self, state: SessionState | None) -> None:
        if state is None:
            self.update("[dim italic]  Select a session to view details[/]")
            self.border_title = "Detail"
            return

        project = Path(state.cwd).name if state.cwd else "?"
        self.border_title = f" Detail ── {project} "

        lines: list[str] = []

        # ── Session ──
        lines.append(_section_header("SESSION"))
        lines.append(_kv("ID", state.session_id))
        lines.append(_kv("Dir", state.cwd))

        # ── Status ──
        lines.append("")
        lines.append(_section_header("STATUS"))
        style = _STATUS_STYLES.get(state.status, "dim")
        indicator = _STATUS_INDICATORS.get(state.status, "●")
        lines.append(
            _kv("Status", f"[{style}]{indicator} {state.status.value.upper()}[/]")
        )
        if state.model:
            lines.append(_kv("Model", state.model))
        lines.append(_kv("Mode", state.permission_mode))
        lines.append(_kv("Term", state.terminal or "?"))

        # ── Timing ──
        lines.append("")
        lines.append(_section_header("TIMING"))
        lines.append(_kv("Up", _format_uptime(state.started_at)))
        lines.append(_kv("Start", state.started_at.strftime("%H:%M")))
        if state.turn_started_at:
            turn_secs = int((utcnow() - state.turn_started_at).total_seconds())
            mins, secs = divmod(turn_secs, 60)
            lines.append(_kv("Since", f"{mins}m{secs:02d}s"))

        # ── Context ──
        if state.context_tokens > 0:
            lines.append("")
            lines.append(_section_header("CONTEXT"))
            limit = _MODEL_LIMITS.get(state.model or "", 200_000)
            lines.append(_context_bar(state.context_tokens, limit))

        # ── Last Prompt ──
        if state.last_prompt:
            lines.append("")
            lines.append(_section_header("LAST PROMPT"))
            lines.append(f"  [italic]{state.last_prompt}[/]")

        # ── Pending Question ──
        pq = state.pending_question
        if pq:
            lines.append("")
            if "questions" in pq:
                lines.append(_section_header("PENDING QUESTION", style="$warning bold"))
                for q in pq["questions"]:
                    lines.append(f"  [italic]{q.get('question', '')}[/]")
                    for opt in q.get("options", []):
                        label = opt.get("label", "")
                        desc = opt.get("description", "")
                        if desc:
                            lines.append(f"    [dim]├─[/] [bold]{label}[/]: {desc}")
                        else:
                            lines.append(f"    [dim]├─[/] [bold]{label}[/]")
            else:
                lines.append(_section_header("PLAN APPROVAL", style="$warning bold"))
                for p in pq.get("allowedPrompts", []):
                    lines.append(f"  [dim]├─[/] {p.get('prompt', '')}")

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
