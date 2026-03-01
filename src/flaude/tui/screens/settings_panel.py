"""Consolidated settings panel — session + notification settings."""

from __future__ import annotations

from enum import Enum, auto
from typing import NamedTuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Input

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


# fmt: off
ROWS: list[_SettingRow] = [
    _SettingRow(_RowKind.HEADER, "Session"),
    _SettingRow(_RowKind.NUMBER, "  Hide idle after (min)", ("soft_hide_minutes",), 30, min_val=1, max_val=STALE_SESSION_TIMEOUT // 60),

    _SettingRow(_RowKind.HEADER, "Notifications"),
    _SettingRow(_RowKind.TOGGLE, "  Master enable",         ("notifications", "enabled"), False),

    _SettingRow(_RowKind.HEADER, "Long Turn Completion"),
    _SettingRow(_RowKind.TOGGLE, "  Enabled",               ("notifications", "long_turn_completion", "enabled"), True),
    _SettingRow(_RowKind.TOGGLE, "  Terminal bell",          ("notifications", "long_turn_completion", "terminal_bell"), True),
    _SettingRow(_RowKind.TOGGLE, "  macOS notification",     ("notifications", "long_turn_completion", "macos_alert"), False),
    _SettingRow(_RowKind.TOGGLE, "  System sound",           ("notifications", "long_turn_completion", "system_sound"), False),
    _SettingRow(_RowKind.NUMBER, "  Timer (minutes)",        ("notifications", "long_turn_completion", "long_turn_minutes"), 5, min_val=0.1),

    _SettingRow(_RowKind.HEADER, "Waiting on Input"),
    _SettingRow(_RowKind.TOGGLE, "  Enabled",               ("notifications", "waiting_on_input", "enabled"), False),
    _SettingRow(_RowKind.TOGGLE, "  Terminal bell",          ("notifications", "waiting_on_input", "terminal_bell"), True),
    _SettingRow(_RowKind.TOGGLE, "  macOS notification",     ("notifications", "waiting_on_input", "macos_alert"), False),
    _SettingRow(_RowKind.TOGGLE, "  System sound",           ("notifications", "waiting_on_input", "system_sound"), False),
    _SettingRow(_RowKind.NUMBER, "  Delay (seconds)",        ("notifications", "waiting_on_input", "delay_seconds"), 10, min_val=1),
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
    .setting-line {
        padding: 0 1;
        height: 1;
    }
    .setting-line-selected {
        padding: 0 1;
        height: 1;
        background: $primary 30%;
    }
    .header-line {
        padding: 0 1;
        height: 1;
        color: $text-muted;
        text-style: bold;
    }
    .number-row {
        height: 3;
        padding: 0 1;
    }
    .number-row-selected {
        height: 3;
        padding: 0 1;
        background: $primary 30%;
    }
    .number-label {
        width: 26;
        padding-top: 1;
    }
    .number-input {
        width: 10;
    }
    #settings-hint {
        margin-top: 1;
        color: $text-muted;
        text-align: center;
    }
    """

    def __init__(self, current: dict) -> None:
        super().__init__()
        self._current = _deep_copy(current)
        self._nav_pos = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Static("Settings", id="settings-title")
            for i, row in enumerate(ROWS):
                if row.kind == _RowKind.HEADER:
                    yield Static(
                        f"[bold]{row.label}[/]", id=f"row-{i}", classes="header-line"
                    )
                elif row.kind == _RowKind.TOGGLE:
                    yield Static("", id=f"row-{i}", classes="setting-line")
                elif row.kind == _RowKind.NUMBER:
                    with Horizontal(id=f"row-{i}", classes="number-row"):
                        yield Static(row.label, classes="number-label")
                        yield Input(
                            value=str(self._get_value(row)),
                            id=f"input-{row.path[-1]}",
                            type="number",
                            classes="number-input",
                        )
            yield Static(
                "[bold]Up[/]/[bold]Down[/] Navigate  "
                "[bold]Tab[/] Toggle  "
                "[bold]Enter[/] Confirm  "
                "[bold]Esc[/] Cancel",
                id="settings-hint",
            )

    def on_mount(self) -> None:
        self._render_all()
        self.set_focus(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self._save()

    # --- Navigation ---

    def action_move_up(self) -> None:
        self._nav_pos = (self._nav_pos - 1) % len(_INTERACTIVE_INDICES)
        self._render_all()
        self._update_focus()

    def action_move_down(self) -> None:
        self._nav_pos = (self._nav_pos + 1) % len(_INTERACTIVE_INDICES)
        self._render_all()
        self._update_focus()

    def action_toggle_item(self) -> None:
        row = ROWS[_INTERACTIVE_INDICES[self._nav_pos]]
        if row.kind == _RowKind.TOGGLE:
            self._set_value(row, not self._get_value(row))
            self._render_all()

    def action_confirm(self) -> None:
        self._save()

    def action_cancel(self) -> None:
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

    def _update_focus(self) -> None:
        row = ROWS[_INTERACTIVE_INDICES[self._nav_pos]]
        if row.kind == _RowKind.NUMBER:
            self.query_one(f"#input-{row.path[-1]}", Input).focus()
        else:
            self.set_focus(None)

    def _render_all(self) -> None:
        selected_row_idx = _INTERACTIVE_INDICES[self._nav_pos]
        for i, row in enumerate(ROWS):
            is_selected = i == selected_row_idx
            widget = self.query_one(f"#row-{i}")

            if row.kind == _RowKind.HEADER:
                continue

            if row.kind == _RowKind.TOGGLE:
                val = self._get_value(row)
                check = "[bold green]ON[/]" if val else "[dim]OFF[/]"
                widget.update(f"  {row.label:<22} {check}")
                widget.set_class(is_selected, "setting-line-selected")
                widget.set_class(not is_selected, "setting-line")

            elif row.kind == _RowKind.NUMBER:
                widget.set_class(is_selected, "number-row-selected")
                widget.set_class(not is_selected, "number-row")

    def _save(self) -> None:
        result = _deep_copy(self._current)
        for row in ROWS:
            if row.kind != _RowKind.NUMBER:
                continue
            try:
                val = float(self.query_one(f"#input-{row.path[-1]}", Input).value)
            except ValueError:
                val = row.default
            val = max(row.min_val, min(row.max_val, val))
            d = result
            for key in row.path[:-1]:
                d = d.setdefault(key, {})
            d[row.path[-1]] = val
        self.dismiss(result)


def _deep_copy(d: dict) -> dict:
    """Recursively copy nested dicts (sufficient for our config structure)."""
    out = dict(d)
    for k, v in out.items():
        if isinstance(v, dict):
            out[k] = _deep_copy(v)
    return out
