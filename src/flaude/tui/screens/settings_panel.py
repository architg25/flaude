"""Consolidated settings panel — session + notification settings."""

from __future__ import annotations

from enum import Enum, auto
from typing import NamedTuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Static

from flaude.constants import STALE_SESSION_TIMEOUT


class _RowKind(Enum):
    TOGGLE = auto()
    NUMBER = auto()
    HEADER = auto()


class _SettingRow(NamedTuple):
    kind: _RowKind
    label: str
    path: tuple[str, ...] = ()
    default: bool | float = False
    min_val: float = 0
    max_val: float = 999
    step: float = 1


# fmt: off
ROWS: list[_SettingRow] = [
    _SettingRow(_RowKind.HEADER, "Session"),
    _SettingRow(_RowKind.NUMBER, "Hide idle after (min)", ("soft_hide_minutes",), 30, min_val=1, max_val=STALE_SESSION_TIMEOUT // 60),

    _SettingRow(_RowKind.HEADER, "Notifications"),
    _SettingRow(_RowKind.TOGGLE, "Master enable",         ("notifications", "enabled"), False),

    _SettingRow(_RowKind.HEADER, "Long Turn Completion"),
    _SettingRow(_RowKind.TOGGLE, "Enabled",               ("notifications", "long_turn_completion", "enabled"), True),
    _SettingRow(_RowKind.TOGGLE, "Terminal bell",          ("notifications", "long_turn_completion", "terminal_bell"), True),
    _SettingRow(_RowKind.TOGGLE, "macOS notification",     ("notifications", "long_turn_completion", "macos_alert"), False),
    _SettingRow(_RowKind.TOGGLE, "System sound",           ("notifications", "long_turn_completion", "system_sound"), False),
    _SettingRow(_RowKind.NUMBER, "Timer (minutes)",        ("notifications", "long_turn_completion", "long_turn_minutes"), 5, min_val=0.1, step=0.5),

    _SettingRow(_RowKind.HEADER, "Waiting on Input"),
    _SettingRow(_RowKind.TOGGLE, "Enabled",               ("notifications", "waiting_on_input", "enabled"), False),
    _SettingRow(_RowKind.TOGGLE, "Terminal bell",          ("notifications", "waiting_on_input", "terminal_bell"), True),
    _SettingRow(_RowKind.TOGGLE, "macOS notification",     ("notifications", "waiting_on_input", "macos_alert"), False),
    _SettingRow(_RowKind.TOGGLE, "System sound",           ("notifications", "waiting_on_input", "system_sound"), False),
    _SettingRow(_RowKind.NUMBER, "Delay (seconds)",        ("notifications", "waiting_on_input", "delay_seconds"), 10, min_val=1),
]
# fmt: on

_INTERACTIVE_INDICES = [i for i, r in enumerate(ROWS) if r.kind != _RowKind.HEADER]


class SettingsPanel(ModalScreen[dict | None]):
    """Unified settings panel with manual Up/Down/Tab/Enter navigation."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("up", "move_up", show=False),
        Binding("down", "move_down", show=False),
        Binding("tab", "toggle_item", show=False),
        Binding("left", "adjust(-1)", show=False),
        Binding("right", "adjust(1)", show=False),
        Binding("enter", "confirm", show=False),
    ]

    DEFAULT_CSS = """
    SettingsPanel {
        align: center middle;
    }
    #settings-dialog {
        width: 60;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    #settings-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    .settings-section {
        height: auto;
        border: heavy $surface-lighten-2;
        border-title-color: $text-muted;
        border-title-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }
    .setting-line {
        height: 1;
    }
    .setting-line-selected {
        height: 1;
        background: $primary 15%;
    }
    .hint-rule {
        color: $text-muted;
        margin-top: 1;
    }
    #settings-hint {
        color: $text-muted;
        text-align: center;
    }
    """

    def __init__(self, current: dict) -> None:
        super().__init__()
        self._current = _deep_copy(current)
        self._nav_pos = 0
        self._editing = False
        self._edit_buf = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Static("Settings", id="settings-title")

            # Group rows into bordered sections delimited by HEADER rows.
            section_label: str | None = None
            section_rows: list[tuple[int, _SettingRow]] = []

            for i, row in enumerate(ROWS):
                if row.kind == _RowKind.HEADER:
                    if section_label is not None:
                        yield from self._compose_section(section_label, section_rows)
                    section_label = row.label
                    section_rows = []
                else:
                    section_rows.append((i, row))

            if section_label is not None:
                yield from self._compose_section(section_label, section_rows)

            yield Static(
                "[dim]\u2500" * 54 + "[/]",
                classes="hint-rule",
            )
            yield Static(
                "[bold]Up[/]/[bold]Down[/] Navigate  \u2502  "
                "[bold]Tab[/] Toggle  \u2502  "
                "[bold]\u2190[/]/[bold]\u2192[/] Adjust  \u2502  "
                "[bold]Enter[/] Confirm  \u2502  "
                "[bold]Esc[/] Cancel",
                id="settings-hint",
            )

    def _compose_section(
        self, label: str, rows: list[tuple[int, _SettingRow]]
    ) -> ComposeResult:
        section = Vertical(classes="settings-section")
        section.border_title = label
        with section:
            for i, _row in rows:
                yield Static("", id=f"row-{i}", classes="setting-line")

    def on_mount(self) -> None:
        self._render_all()
        self.set_focus(None)

    def on_key(self, event: Key) -> None:
        """Capture digit/dot/backspace for inline number editing."""
        row = ROWS[_INTERACTIVE_INDICES[self._nav_pos]]
        if row.kind != _RowKind.NUMBER:
            return

        if event.character and event.character in "0123456789.":
            event.prevent_default()
            event.stop()
            if not self._editing:
                self._editing = True
                self._edit_buf = ""
            self._edit_buf += event.character
            self._render_all()
        elif event.key == "backspace" and self._editing:
            event.prevent_default()
            event.stop()
            self._edit_buf = self._edit_buf[:-1]
            if not self._edit_buf:
                self._editing = False
            self._render_all()

    # --- Navigation ---

    def action_move_up(self) -> None:
        self._commit_edit()
        self._nav_pos = (self._nav_pos - 1) % len(_INTERACTIVE_INDICES)
        self._render_all()

    def action_move_down(self) -> None:
        self._commit_edit()
        self._nav_pos = (self._nav_pos + 1) % len(_INTERACTIVE_INDICES)
        self._render_all()

    def action_toggle_item(self) -> None:
        row = ROWS[_INTERACTIVE_INDICES[self._nav_pos]]
        if row.kind == _RowKind.TOGGLE:
            self._set_value(row, not self._get_value(row))
            self._render_all()
        elif row.kind == _RowKind.NUMBER:
            if self._editing:
                self._commit_edit()
            else:
                self._adjust_number(row, 1)

    def action_adjust(self, direction: int) -> None:
        row = ROWS[_INTERACTIVE_INDICES[self._nav_pos]]
        if row.kind == _RowKind.NUMBER:
            self._commit_edit()
            self._adjust_number(row, direction)

    def action_confirm(self) -> None:
        self._commit_edit()
        self.dismiss(_deep_copy(self._current))

    def action_cancel(self) -> None:
        self._editing = False
        self._edit_buf = ""
        self.dismiss(None)

    # --- Helpers ---

    def _get_value(self, row: _SettingRow):
        d = self._current
        for key in row.path[:-1]:
            d = d.get(key, {})
        return d.get(row.path[-1], row.default)

    def _set_value(self, row: _SettingRow, value) -> None:
        d = self._current
        for key in row.path[:-1]:
            d = d.setdefault(key, {})
        d[row.path[-1]] = value

    def _adjust_number(self, row: _SettingRow, direction: int) -> None:
        val = float(self._get_value(row))
        val = round(val + row.step * direction, 2)
        val = max(row.min_val, min(row.max_val, val))
        self._set_value(row, val)
        self._render_all()

    def _commit_edit(self) -> None:
        """Parse the edit buffer and apply it to the current number row."""
        if not self._editing:
            return
        row = ROWS[_INTERACTIVE_INDICES[self._nav_pos]]
        try:
            val = float(self._edit_buf)
        except ValueError:
            val = float(self._get_value(row))
        val = max(row.min_val, min(row.max_val, val))
        self._set_value(row, val)
        self._editing = False
        self._edit_buf = ""

    def _render_all(self) -> None:
        selected_row_idx = _INTERACTIVE_INDICES[self._nav_pos]
        for i, row in enumerate(ROWS):
            if row.kind == _RowKind.HEADER:
                continue

            is_selected = i == selected_row_idx
            widget = self.query_one(f"#row-{i}")
            cursor = "[bold]>[/] " if is_selected else "  "

            if row.kind == _RowKind.TOGGLE:
                val = self._get_value(row)
                check = "[bold green]\\[x][/]" if val else "[dim]\\[ ][/]"
                widget.update(f"{cursor}{row.label:<34} {check}")

            elif row.kind == _RowKind.NUMBER:
                if is_selected and self._editing:
                    display = f"[bold underline]{self._edit_buf}[/]\u2588"
                    widget.update(f"{cursor}{row.label:<30}   {display}")
                elif is_selected:
                    val = _fmt_num(self._get_value(row))
                    widget.update(
                        f"{cursor}{row.label:<30} "
                        f"[dim]\u25c0[/] [bold]{val}[/] [dim]\u25b6[/]"
                    )
                else:
                    val = _fmt_num(self._get_value(row))
                    widget.update(f"{cursor}{row.label:<34} {val}")

            widget.set_class(is_selected, "setting-line-selected")
            widget.set_class(not is_selected, "setting-line")


def _fmt_num(val) -> str:
    """Format a number for display — drop '.0' from whole numbers."""
    return str(int(val)) if isinstance(val, float) and val == int(val) else str(val)


def _deep_copy(d: dict) -> dict:
    """Recursively copy nested dicts (sufficient for our config structure)."""
    out = dict(d)
    for k, v in out.items():
        if isinstance(v, dict):
            out[k] = _deep_copy(v)
    return out
