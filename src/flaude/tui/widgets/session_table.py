"""Session list widget — DataTable of active Claude Code sessions."""

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual.widgets import DataTable

from flaude.constants import utcnow, get_model_limit
from flaude.formatting import format_uptime, format_compact_duration, format_token_count
from flaude.state.models import SessionState, SessionStatus, STATUS_INFO


def _format_name(state: SessionState) -> Text:
    """Return the display name for the Name column.

    Custom titles (set via /rename) are shown as-is.
    Sessions without a custom title show "[default]" (dim).
    Text objects are used to prevent Rich markup interpretation.
    """
    if state.custom_title:
        return Text(state.custom_title)
    return Text("[default]", style="dim")


def _build_row_data(
    state: SessionState,
    now: datetime,
    css: dict,
    tree_prefix: str = "",
    include_name: bool = False,
) -> tuple:
    """Build the cell values for a session row.

    Returns 8 cells when include_name is True, 7 otherwise.
    """
    info = STATUS_INFO[state.status]
    color = css.get(info.theme_var, "")
    style = f"{color} bold" if info.bold else color
    if state.status == SessionStatus.WORKING and state.turn_started_at:
        duration = format_compact_duration(now, state.turn_started_at)
    else:
        duration = format_compact_duration(now, state.last_event_at)
    status_text = Text(
        f"{tree_prefix}{info.indicator} {info.label} {duration}", style=style
    )
    project = Path(state.cwd).name if state.cwd else "?"
    uptime = format_uptime(now, state.started_at)
    term = state.terminal or "?"
    mode = state.permission_mode or "default"
    context = _format_context(state.context_tokens, state.model, css)
    label = state.agent_name if state.agent_name else state.session_id[:8]
    if include_name:
        name = _format_name(state)
        return status_text, name, label, project[:20], term, mode, context, uptime
    return status_text, label, project[:20], term, mode, context, uptime


def _sort_sessions(sessions: dict[str, SessionState]) -> list[SessionState]:
    """Sort sessions so team members appear right after their parent."""
    by_id = sessions

    # Group team members by lead_session_id
    team_members: dict[str, list[SessionState]] = defaultdict(list)
    standalone: list[SessionState] = []

    for s in sessions.values():
        if s.lead_session_id and s.lead_session_id in by_id:
            team_members[s.lead_session_id].append(s)
        else:
            standalone.append(s)

    # Sort standalone (includes team leads) by normal priority
    standalone.sort(key=lambda s: (STATUS_INFO[s.status].sort_priority, s.started_at))

    # Sort each team's members by agent name
    for members in team_members.values():
        members.sort(key=lambda s: s.agent_name or "")

    # Interleave: after each parent, insert its team members
    result: list[SessionState] = []
    for s in standalone:
        result.append(s)
        if s.session_id in team_members:
            result.extend(team_members[s.session_id])

    return result


def _compute_tree_prefixes(sorted_sessions: list[SessionState]) -> dict[str, str]:
    """Compute tree connector prefixes for the Status column.

    Team members get ├ or └ prefix. Others get empty string.
    """
    prefixes: dict[str, str] = {}

    # Count team members per lead to know which is last
    team_counts: dict[str, int] = defaultdict(int)
    for s in sorted_sessions:
        if s.lead_session_id and s.agent_name:
            team_counts[s.lead_session_id] += 1

    team_seen: dict[str, int] = defaultdict(int)
    for s in sorted_sessions:
        if s.agent_name and s.lead_session_id:
            team_seen[s.lead_session_id] += 1
            is_last = team_seen[s.lead_session_id] == team_counts[s.lead_session_id]
            prefixes[s.session_id] = "└ " if is_last else "├ "
        else:
            prefixes[s.session_id] = ""

    return prefixes


class SessionTable(DataTable):
    """Table showing all active sessions."""

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self._has_name_col = False
        self._col_keys = self.add_columns(
            "Status", "Session", "Project", "Terminal", "Mode", "Context", "Uptime"
        )
        self._last_order: list[str] = []
        self.border_title = "Sessions"

    def _rebuild_columns(self, include_name: bool) -> None:
        """Clear and re-add columns when Name column visibility changes."""
        self.clear(columns=True)
        self._last_order = []
        self._has_name_col = include_name
        if include_name:
            self._col_keys = self.add_columns(
                "Status", "Name", "Session", "Project", "Terminal", "Mode", "Context", "Uptime"
            )
        else:
            self._col_keys = self.add_columns(
                "Status", "Session", "Project", "Terminal", "Mode", "Context", "Uptime"
            )

    def update_sessions(
        self,
        sessions: dict[str, SessionState],
        hidden_count: int = 0,
        any_named: bool = False,
    ) -> None:
        selected_key = self.get_selected_session_id()

        if not sessions:
            if self._last_order:
                # Transition to empty state
                self.clear()
                self._last_order = []
            if self.row_count == 0:
                self.add_row(
                    Text("No sessions", style="dim"),
                    "",
                    Text(
                        "press n or start claude · existing sessions appear after their next hook fires · run flaude init if hooks not set up",
                        style="dim italic",
                    ),
                    "",
                    "",
                    "",
                    "",
                )
            return

        should_have_name = any_named or any(s.custom_title for s in sessions.values())
        if should_have_name != self._has_name_col:
            self._rebuild_columns(should_have_name)

        sorted_sessions = _sort_sessions(sessions)
        new_order = [s.session_id for s in sorted_sessions]
        prefixes = _compute_tree_prefixes(sorted_sessions)

        now = utcnow()
        css = self.app.get_css_variables()

        if new_order == self._last_order:
            # Fast path: in-place cell updates (no DOM teardown)
            for state in sorted_sessions:
                cells = _build_row_data(
                    state, now, css, prefixes.get(state.session_id, ""),
                    include_name=self._has_name_col,
                )
                for col_key, value in zip(self._col_keys, cells):
                    self.update_cell(state.session_id, col_key, value)
        else:
            # Slow path: sessions added/removed/reordered — full rebuild
            self.clear()
            for state in sorted_sessions:
                cells = _build_row_data(
                    state, now, css, prefixes.get(state.session_id, ""),
                    include_name=self._has_name_col,
                )
                self.add_row(*cells, key=state.session_id)
            self._last_order = new_order

            # Restore cursor to previously selected row
            if selected_key:
                for idx, sid in enumerate(new_order):
                    if sid == selected_key:
                        self.move_cursor(row=idx)
                        break

        if hidden_count:
            self.border_subtitle = (
                f" {len(sorted_sessions)} active ({hidden_count} hidden) "
            )
        else:
            self.border_subtitle = f" {len(sorted_sessions)} active "

    def get_selected_session_id(self) -> str | None:
        """Return the session_id of the currently highlighted row."""
        if self.row_count == 0:
            return None
        row_key, _ = self.coordinate_to_cell_key(self.cursor_coordinate)
        return str(row_key.value) if row_key else None


def _format_context(tokens: int, model: str | None, css: dict) -> Text:
    if tokens <= 0:
        return Text("─", style=css.get("text-muted", "dim"))
    label = format_token_count(tokens)
    limit = get_model_limit(model)
    ratio = tokens / limit if limit else 0
    if ratio > 0.8:
        style = f"{css.get('error', 'red')} bold"
    elif ratio > 0.5:
        style = css.get("warning", "yellow")
    else:
        style = css.get("success", "green")
    return Text(label, style=style)
