"""Session detail panel — shows info about the selected session."""

from pathlib import Path

from textual.widgets import Static

from flaude.constants import utcnow, get_model_limit
from flaude.formatting import format_uptime, format_token_count
from flaude.state.models import SessionState, STATUS_INFO


def _kv(label: str, value: str, label_width: int = 8) -> str:
    """Render a key-value pair with dim label."""
    return f"  [dim]{label:<{label_width}}[/] {value}"


_EIGHTHS = " ▏▎▍▌▋▊▉█"


def _context_bar(tokens: int, limit: int, width: int = 20) -> str:
    """Render a sub-character smooth progress bar with token counts."""
    ratio = min(tokens / limit, 1.0) if limit else 0

    if ratio > 0.8:
        bar_style = "$error"
    elif ratio > 0.5:
        bar_style = "$warning"
    else:
        bar_style = "$success"

    # Sub-character precision: each cell has 8 gradations
    total = ratio * width
    full = int(total)
    frac = int((total - full) * 8)
    empty = width - full - (1 if frac else 0)

    bar = "█" * full
    if frac:
        bar += _EIGHTHS[frac]
    trail = "░" * empty

    ctx_str = format_token_count(tokens)
    if limit >= 1_000_000:
        limit_str = f"{limit // 1_000_000}M"
    else:
        limit_str = f"{limit // 1_000}K"

    return f"  [{bar_style}]{bar}[/][dim]{trail}[/]  [{bar_style}]{ctx_str}[/] [dim]/ {limit_str}[/]"


def _sep() -> str:
    """Dim separator line."""
    return "[dim]  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─[/]"


class SessionDetail(Static):
    """Displays detailed info for the selected session."""

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)

    def update_session(
        self,
        state: SessionState | None,
        group_names: dict[str, str] | None = None,
        session_groups: dict[str, str] | None = None,
    ) -> None:
        if state is None:
            self.update("[dim italic]  Select a session[/]")
            self.border_title = "Detail"
            return

        if state.git_repo_root:
            repo_display = (group_names or {}).get(state.git_repo_root) or Path(
                state.git_repo_root
            ).name
        else:
            repo_display = None
        project = repo_display or (Path(state.cwd).name if state.cwd else "?")
        self.border_title = f" {project} "

        lines: list[str] = []

        # ── Status + identity block ──
        info = STATUS_INFO[state.status]
        style = f"${info.theme_var} bold" if info.bold else f"${info.theme_var}"
        lines.append(f"  [{style}]{info.indicator} {info.label}[/]")
        lines.append(_kv("Model", f"[dim]{state.model or '?'}[/]"))
        lines.append(_kv("Mode", state.permission_mode or "default"))
        uptime = format_uptime(utcnow(), state.started_at)
        start = state.started_at.strftime("%H:%M")
        lines.append(_kv("Up", f"{uptime} [dim]· {start}[/]"))
        if state.turn_started_at:
            turn_secs = int((utcnow() - state.turn_started_at).total_seconds())
            mins, secs = divmod(turn_secs, 60)
            lines.append(_kv("Turn", f"{mins}m{secs:02d}s"))

        # ── Context bar ──
        if state.context_tokens > 0:
            lines.append("")
            limit = get_model_limit(state.model)
            lines.append(_context_bar(state.context_tokens, limit))

        # ── Location ──
        lines.append("")
        lines.append(_sep())
        lines.append("")
        lines.append(_kv("Dir", f"[dim]{state.cwd}[/]"))
        if state.git_repo_root:
            lines.append(_kv("Branch", state.git_branch or "[dim]detached[/]"))
            if state.git_is_worktree:
                lines.append(_kv("Tree", f"[dim]{state.cwd}[/]"))
        if state.is_tmux:
            parent = state.parent_terminal or "?"
            lines.append(_kv("Term", f"{parent} [dim]· tmux[/]"))
        else:
            lines.append(_kv("Term", state.terminal or "?"))
        lines.append(_kv("ID", f"[dim]{state.session_id}[/]"))
        if state.custom_title:
            lines.append(_kv("Name", state.custom_title))
        manual_group = (session_groups or {}).get(state.session_id)
        if manual_group:
            lines.append(_kv("Group", manual_group))

        # ── Team ──
        if state.team_name:
            lines.append("")
            lines.append(_sep())
            lines.append("")
            lines.append(_kv("Team", state.team_name))
            if state.agent_name:
                lines.append(_kv("Role", state.agent_name))
            if state.lead_session_id:
                lines.append(_kv("Lead", f"[dim]{state.lead_session_id[:8]}[/]"))

        # ── Last Prompt ──
        if state.last_prompt:
            lines.append("")
            lines.append(_sep())
            lines.append("")
            prompt = state.last_prompt
            if len(prompt) > 80:
                prompt = prompt[:77] + "..."
            lines.append(f"  [italic]{prompt}[/]")

        # ── Pending Question ──
        pq = state.pending_question
        if pq:
            lines.append("")
            lines.append(_sep())
            lines.append("")
            if "questions" in pq:
                lines.append("  [$warning bold]Pending Question[/]")
                for q in pq["questions"]:
                    lines.append(f"  [italic]{q.get('question', '')}[/]")
                    for opt in q.get("options", []):
                        label = opt.get("label", "")
                        desc = opt.get("description", "")
                        if desc:
                            lines.append(f"    [dim]·[/] [bold]{label}[/]  {desc}")
                        else:
                            lines.append(f"    [dim]·[/] [bold]{label}[/]")
            else:
                lines.append("  [$warning bold]Plan Approval[/]")
                for p in pq.get("allowedPrompts", []):
                    lines.append(f"  [dim]·[/] {p.get('prompt', '')}")

        content = "\n".join(lines)
        if content != getattr(self, "_last_content", None):
            self._last_content = content
            self.update(content)
