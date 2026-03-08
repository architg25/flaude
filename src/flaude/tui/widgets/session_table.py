"""Session list widget — DataTable of active Claude Code sessions."""

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from rich.console import Console, ConsoleOptions, RenderResult
from rich.measure import Measurement
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual._types import SegmentLines
from textual.coordinate import Coordinate
from textual.widgets import DataTable

from flaude.constants import utcnow, get_model_limit
from flaude.formatting import format_uptime, format_compact_duration, format_token_count
from flaude.state.models import SessionState, SessionStatus, STATUS_INFO


REPO_HEADER_PREFIX = "__repo__"
GROUP_HEADER_PREFIX = "__group__"


class _ZeroWidthText:
    """Renderable that displays text but reports zero width for measurement.

    Prevents group header names from inflating DataTable column widths.
    """

    def __init__(self, text: Text) -> None:
        self.text = text

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield self.text

    def __rich_measure__(
        self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        return Measurement(0, 0)


_STYLE_DIM = Style(dim=True)
_STYLE_BOLD = Style(bold=True)


def _header_text(display: str) -> _ZeroWidthText:
    return _ZeroWidthText(Text(f" {display}", style="bold"))


def _format_project(state: SessionState, max_len: int = 22) -> str:
    """Format the Project column value.

    Shows 'repo-name (branch)' for git repos, truncating the repo name
    with an ellipsis when the full string exceeds *max_len* so the branch
    stays visible.  Falls back to CWD basename for non-git sessions.
    """
    if state.git_repo_root:
        repo_name = Path(state.git_repo_root).name
        branch = state.git_branch or "detached"
        full = f"{repo_name} ({branch})"
        if len(full) <= max_len:
            return full
        suffix = f" ({branch})"
        avail = max_len - len(suffix) - 1  # 1 for ellipsis
        if avail >= 4:
            return f"{repo_name[:avail]}…{suffix}"
        return full[:max_len]
    return Path(state.cwd).name if state.cwd else "?"


def _format_session_identity(state: SessionState) -> str:
    """Format the Session column: custom_title (agent_name) > agent_name > session_id[:8].

    When a custom title exists, show it with the underlying identifier in parens.
    """
    base = state.agent_name if state.agent_name else state.session_id[:8]
    if state.custom_title:
        title = state.custom_title
        if len(title) > 20:
            title = title[:19] + "…"
        return f"{title} ({base})"
    return base


_TERMINAL_ABBREV = {
    "iTerm2": "iT2",
    "Ghostty": "Gh",
    "Terminal": "Trm",
    "Warp": "Wrp",
    "IntelliJ": "ItJ",
}

_MODE_ABBREV = {
    "default": "─",
    "plan": "plan",
    "acceptEdits": "edit",
}


def _abbrev_terminal(name: str) -> str:
    return _TERMINAL_ABBREV.get(name, name)


def _abbrev_mode(mode: str) -> str:
    return _MODE_ABBREV.get(mode, mode)


def _build_row_data(
    state: SessionState,
    now: datetime,
    css: dict,
    tree_prefix: str = "",
) -> tuple:
    """Build the 5 cell values for a session row."""
    info = STATUS_INFO[state.status]
    color = css.get(info.theme_var, "")
    style = f"{color} bold" if info.bold else color
    if state.status == SessionStatus.WORKING and state.turn_started_at:
        duration = format_compact_duration(now, state.turn_started_at)
    else:
        duration = format_compact_duration(now, state.last_event_at)
    status_text = Text(
        f"{tree_prefix}{info.indicator} {info.label} {duration}",
        style=style,
        justify="center",
    )
    session = Text(_format_session_identity(state), justify="center")
    project = Text(_format_project(state), justify="center")

    # Environment: abbreviated terminal + mode (only if non-default)
    if state.is_tmux:
        parent = state.parent_terminal or "?"
        term = f"{_abbrev_terminal(parent)}|tmux"
    else:
        term = _abbrev_terminal(state.terminal or "?")
    mode = _abbrev_mode(state.permission_mode or "default")
    environment = Text(f"{term:<3} | {mode}", justify="center")

    # Usage: context tokens (colored) · uptime (dim)
    context = _format_context(state.context_tokens, state.model, css)
    uptime = format_uptime(now, state.started_at)
    usage = Text.assemble(context, Text(f" | {uptime}", style="dim"))
    usage.justify = "center"

    return status_text, session, project, environment, usage


def _session_group_key(
    s: SessionState,
    auto_group: bool,
    session_groups: dict[str, str] | None,
) -> str | None:
    """Return the group key for a session, or None if ungrouped."""
    manual = (session_groups or {}).get(s.session_id)
    if manual:
        return f"{GROUP_HEADER_PREFIX}{manual}"
    if auto_group and s.git_repo_root:
        return f"{REPO_HEADER_PREFIX}{s.git_repo_root}"
    return None


def _sort_sessions(
    sessions: dict[str, SessionState],
    auto_group: bool = True,
    session_groups: dict[str, str] | None = None,
) -> list[SessionState]:
    """Sort sessions: grouped by repo/manual group, sorted within each group.

    Groups are stable — status changes only reorder within a group, never
    cause a session to jump between groups.
    """
    # Separate team members from standalone sessions
    team_members: dict[str, list[SessionState]] = defaultdict(list)
    standalone: list[SessionState] = []

    for s in sessions.values():
        if s.lead_session_id and s.lead_session_id in sessions:
            team_members[s.lead_session_id].append(s)
        else:
            standalone.append(s)

    # Bucket standalone sessions by group key
    group_buckets: dict[str, list[SessionState]] = defaultdict(list)
    ungrouped: list[SessionState] = []
    for s in standalone:
        key = _session_group_key(s, auto_group, session_groups)
        if key:
            group_buckets[key].append(s)
        else:
            ungrouped.append(s)

    # Sort within each bucket by status priority, then start time
    sort_key = lambda s: (STATUS_INFO[s.status].sort_priority, s.started_at)
    ungrouped.sort(key=sort_key)
    for bucket in group_buckets.values():
        bucket.sort(key=sort_key)

    # Stable group order: by earliest session start time in each group
    ordered_groups = sorted(
        group_buckets, key=lambda g: min(s.started_at for s in group_buckets[g])
    )

    # Sort team members
    for members in team_members.values():
        members.sort(key=lambda s: s.agent_name or "")

    # Assemble: ungrouped first, then each group
    result: list[SessionState] = []
    for s in ungrouped:
        result.append(s)
        if s.session_id in team_members:
            result.extend(team_members[s.session_id])
    for group in ordered_groups:
        for s in group_buckets[group]:
            result.append(s)
            if s.session_id in team_members:
                result.extend(team_members[s.session_id])

    return result


def _group_display_names(
    group_keys: set[str],
    group_names: dict[str, str] | None = None,
) -> dict[str, str]:
    """Map group keys to display names.

    Repo groups (``__repo__<path>``) get auto-named from the path with
    disambiguation, overridden by *group_names*.  Manual groups
    (``__group__<name>``) use the name directly.
    """
    names: dict[str, str] = {}
    repo_roots: set[str] = set()
    for key in group_keys:
        if key.startswith(GROUP_HEADER_PREFIX):
            names[key] = key.removeprefix(GROUP_HEADER_PREFIX)
        elif key.startswith(REPO_HEADER_PREFIX):
            repo_roots.add(key.removeprefix(REPO_HEADER_PREFIX))

    # Resolve repo display names with user overrides + disambiguation
    remaining: set[str] = set()
    for root in repo_roots:
        custom = (group_names or {}).get(root)
        if custom:
            names[f"{REPO_HEADER_PREFIX}{root}"] = custom
        else:
            remaining.add(root)
    name_to_roots: dict[str, list[str]] = defaultdict(list)
    for root in remaining:
        name_to_roots[Path(root).name].append(root)
    for name, paths in name_to_roots.items():
        if len(paths) == 1:
            names[f"{REPO_HEADER_PREFIX}{paths[0]}"] = name
        else:
            for p in paths:
                parent = Path(p).parent.name
                names[f"{REPO_HEADER_PREFIX}{p}"] = f"{parent}/{name}"
    return names


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
        self._col_keys = self.add_columns(
            Text("Status", justify="center"),
            Text("Session", justify="center"),
            Text("Project", justify="center"),
            Text("Env", justify="center"),
            Text("Usage", justify="center"),
        )
        self._last_order: list[str] = []
        self.border_title = "Sessions"

    def _render_line_in_row(
        self,
        row_key,
        line_no: int,
        base_style: Style,
        cursor_location: Coordinate,
        hover_location: Coordinate,
    ) -> tuple[SegmentLines, SegmentLines]:
        """Render group header rows as full-width dividers.

        WARNING: This reimplements DataTable._render_line_in_row internals
        (cache keys, style resolution, row extension). Must be audited on
        Textual upgrades.  See update_sessions() for the height=1/2 convention
        that controls whether a spacer line appears above the divider.
        """
        key_val = row_key.value
        if key_val is None or not self._is_header_key(key_val):
            return super()._render_line_in_row(
                row_key, line_no, base_style, cursor_location, hover_location
            )

        cache_key = (
            row_key,
            line_no,
            base_style,
            cursor_location,
            hover_location,
            self.cursor_type,
            self.show_cursor,
            self._show_hover_cursor,
            self._update_count,
            self._pseudo_class_state,
        )
        if cache_key in self._row_render_cache:
            return self._row_render_cache[cache_key]

        row_index = self._row_locations.get(row_key)
        should_highlight = self._should_highlight

        # Total scrollable width across all columns
        total_width = sum(col.get_render_width(self) for col in self.ordered_columns)

        # Cursor/hover styling
        row_style = self._get_row_style(row_index, base_style)
        is_cursor = should_highlight(
            cursor_location, Coordinate(row_index, 0), self.cursor_type
        )
        is_hover = should_highlight(
            hover_location, Coordinate(row_index, 0), self.cursor_type
        )
        component_style, post_style = self._get_styles_to_render_cell(
            False,
            False,
            False,
            is_hover,
            is_cursor,
            self.show_cursor,
            self._show_hover_cursor,
            self.cursor_foreground_priority == "css",
            self.cursor_background_priority == "css",
        )
        combined_style = row_style + component_style + post_style

        # Row is 2 lines tall for non-first groups: line 0 = blank spacer,
        # line 1 = divider.  First group has height=1, so line_no is always 0.
        is_divider_line = (self.rows[row_key].height == 1) or (line_no == 1)

        if is_divider_line:
            # " ── name ──────…" divider spanning all columns
            name = self._data[row_key][self._col_keys[0]].text.plain.strip()
            rule_style = _STYLE_DIM + combined_style
            label_style = _STYLE_BOLD + combined_style
            pad = self.cell_padding
            prefix = f"{' ' * pad}── "
            suffix = " "
            fill_len = max(0, total_width - len(prefix) - len(name) - len(suffix))
            segments = [
                Segment(prefix, rule_style),
                Segment(name, label_style),
                Segment(suffix + "─" * fill_len, rule_style),
            ]
            line = Segment.adjust_line_length(
                segments, total_width, style=combined_style
            )
        else:
            # Blank spacer line (line 0 of height-2 header rows)
            line = [Segment(" " * total_width, combined_style)]

        scrollable_row: list[list[Segment]] = [line]

        # Fill remaining space to the right of the table
        widget_width = self.size.width
        remaining = max(0, widget_width - total_width - self._row_label_column_width)
        if remaining:
            extend_style = combined_style + Style.from_meta(
                {"row": row_index, "column": 0, "out_of_bounds": True}
            )
            scrollable_row.append([Segment(" " * remaining, extend_style)])

        fixed_row: list[list[Segment]] = []
        row_pair = (fixed_row, scrollable_row)
        self._row_render_cache[cache_key] = row_pair
        return row_pair

    def update_sessions(
        self,
        sessions: dict[str, SessionState],
        hidden_count: int = 0,
        group_names: dict[str, str] | None = None,
        auto_group: bool = True,
        session_groups: dict[str, str] | None = None,
    ) -> None:
        selected_key = self.get_selected_session_id()

        if not sessions:
            if self._last_order:
                self.clear()
                self._last_order = []
            return

        sorted_sessions = _sort_sessions(sessions, auto_group, session_groups)
        prefixes = _compute_tree_prefixes(sorted_sessions)

        # Compute group key for each session once
        session_group_map = {
            s.session_id: _session_group_key(s, auto_group, session_groups)
            for s in sorted_sessions
        }
        display_names = _group_display_names(
            {g for g in session_group_map.values() if g}, group_names
        )

        # Build ordered list of keys including group header sentinels
        new_order: list[str] = []
        last_group: str | None = None
        for s in sorted_sessions:
            group = session_group_map[s.session_id]
            if group and group != last_group:
                new_order.append(group)
                last_group = group
            elif not group and last_group is not None:
                last_group = None
            new_order.append(s.session_id)

        now = utcnow()
        css = self.app.get_css_variables()
        num_cols = len(self._col_keys)

        if new_order == self._last_order:
            # Fast path: in-place cell updates
            for state in sorted_sessions:
                cells = _build_row_data(
                    state,
                    now,
                    css,
                    prefixes.get(state.session_id, ""),
                )
                for col_key, value in zip(self._col_keys, cells):
                    self.update_cell(state.session_id, col_key, value)
            # Update header row labels (names may have changed)
            for key in new_order:
                if key in display_names:
                    header_text = _header_text(display_names[key])
                    self.update_cell(key, self._col_keys[0], header_text)
        else:
            # Slow path: sessions added/removed/reordered — full rebuild
            self.clear()
            last_group = None
            row_idx = 0
            for state in sorted_sessions:
                group = session_group_map[state.session_id]
                if group and group != last_group:
                    display = display_names.get(group, "?")
                    header_text = _header_text(display)
                    empty_cells = [""] * (num_cols - 1)
                    # height=2 adds a blank spacer line above the divider;
                    # height=1 for the first row.  See _render_line_in_row.
                    h = 1 if row_idx == 0 else 2
                    self.add_row(header_text, *empty_cells, height=h, key=group)
                    last_group = group
                    row_idx += 1
                elif not group and last_group is not None:
                    last_group = None
                cells = _build_row_data(
                    state,
                    now,
                    css,
                    prefixes.get(state.session_id, ""),
                )
                self.add_row(*cells, key=state.session_id)
                row_idx += 1
            self._last_order = new_order

            # Restore cursor to previously selected row
            if selected_key:
                for idx, key in enumerate(new_order):
                    if key == selected_key:
                        self.move_cursor(row=idx)
                        break

        if hidden_count:
            self.border_subtitle = (
                f" {len(sorted_sessions)} active ({hidden_count} hidden) "
            )
        else:
            self.border_subtitle = f" {len(sorted_sessions)} active "

    def _get_cursor_row_key(self) -> str | None:
        """Return the raw row key string at the cursor position."""
        if self.row_count == 0:
            return None
        row_key, _ = self.coordinate_to_cell_key(self.cursor_coordinate)
        return str(row_key.value) if row_key else None

    def _is_header_key(self, key: str) -> bool:
        return key.startswith(REPO_HEADER_PREFIX) or key.startswith(GROUP_HEADER_PREFIX)

    def get_selected_session_id(self) -> str | None:
        """Return the session_id of the currently highlighted row.

        Returns None for group header rows.
        """
        key = self._get_cursor_row_key()
        if not key or self._is_header_key(key):
            return None
        return key

    def get_selected_header_key(self) -> str | None:
        """Return the full header key if cursor is on a group header row."""
        key = self._get_cursor_row_key()
        if key and self._is_header_key(key):
            return key
        return None


def _format_context(tokens: int, model: str | None, css: dict) -> Text:
    if tokens <= 0:
        return Text(f"{'─':>4}", style=css.get("text-muted", "dim"))
    label = format_token_count(tokens)
    limit = get_model_limit(model)
    ratio = tokens / limit if limit else 0
    if ratio > 0.8:
        style = f"{css.get('error', 'red')} bold"
    elif ratio > 0.5:
        style = css.get("warning", "yellow")
    else:
        style = css.get("success", "green")
    return Text(f"{label:>4}", style=style)
