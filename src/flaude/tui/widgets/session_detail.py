"""Session detail panel — shows info about the selected session."""

from pathlib import Path

from textual.widgets import Static

from flaude.constants import utcnow, get_model_limit
from flaude.formatting import format_uptime, format_token_count
from flaude.state.models import SessionState, STATUS_INFO


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

    ctx_str = format_token_count(tokens)
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
        if state.custom_title:
            lines.append(_kv("Name", state.custom_title))
        lines.append(_kv("Dir", state.cwd))

        # ── Team ──
        if state.team_name:
            lines.append("")
            lines.append(_section_header("TEAM"))
            lines.append(_kv("Team", state.team_name))
            if state.agent_name:
                lines.append(_kv("Role", state.agent_name))
            if state.lead_session_id:
                lines.append(_kv("Lead", state.lead_session_id[:8]))

        # ── Status ──
        lines.append("")
        lines.append(_section_header("STATUS"))
        info = STATUS_INFO[state.status]
        style = f"${info.theme_var} bold" if info.bold else f"${info.theme_var}"
        lines.append(_kv("Status", f"[{style}]{info.indicator} {info.label}[/]"))
        if state.model:
            lines.append(_kv("Model", state.model))
        lines.append(_kv("Mode", state.permission_mode or "default"))
        lines.append(_kv("Term", state.terminal or "?"))

        # ── Timing ──
        lines.append("")
        lines.append(_section_header("TIMING"))
        lines.append(_kv("Up", format_uptime(utcnow(), state.started_at)))
        lines.append(_kv("Start", state.started_at.strftime("%H:%M")))
        if state.turn_started_at:
            turn_secs = int((utcnow() - state.turn_started_at).total_seconds())
            mins, secs = divmod(turn_secs, 60)
            lines.append(_kv("Since", f"{mins}m{secs:02d}s"))

        # ── Context ──
        if state.context_tokens > 0:
            lines.append("")
            lines.append(_section_header("CONTEXT"))
            limit = get_model_limit(state.model)
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

        content = "\n".join(lines)
        if content != getattr(self, "_last_content", None):
            self._last_content = content
            self.update(content)
