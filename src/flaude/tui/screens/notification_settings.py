"""Notification settings dialog — two-category layout with manual navigation."""

from __future__ import annotations

from enum import Enum, auto
from typing import NamedTuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Input


class _RowKind(Enum):
    TOGGLE = auto()
    NUMBER = auto()
    HEADER = auto()  # non-interactive section divider


class _SettingRow(NamedTuple):
    kind: _RowKind
    label: str
    category: str | None = None  # None = top-level key
    key: str | None = None
    default: bool | float = False


# fmt: off
ROWS: list[_SettingRow] = [
    _SettingRow(_RowKind.TOGGLE, "Master enable",        None, "enabled", False),
    _SettingRow(_RowKind.HEADER, "Long Turn Completion"),
    _SettingRow(_RowKind.TOGGLE, "  Enabled",            "long_turn_completion", "enabled", True),
    _SettingRow(_RowKind.TOGGLE, "  Terminal bell",      "long_turn_completion", "terminal_bell", True),
    _SettingRow(_RowKind.TOGGLE, "  macOS notification", "long_turn_completion", "macos_alert", False),
    _SettingRow(_RowKind.TOGGLE, "  System sound",       "long_turn_completion", "system_sound", False),
    _SettingRow(_RowKind.NUMBER, "  Timer (minutes)",    "long_turn_completion", "long_turn_minutes", 5),
    _SettingRow(_RowKind.HEADER, "Waiting on Input"),
    _SettingRow(_RowKind.TOGGLE, "  Enabled",            "waiting_on_input", "enabled", False),
    _SettingRow(_RowKind.TOGGLE, "  Terminal bell",      "waiting_on_input", "terminal_bell", True),
    _SettingRow(_RowKind.TOGGLE, "  macOS notification", "waiting_on_input", "macos_alert", False),
    _SettingRow(_RowKind.TOGGLE, "  System sound",       "waiting_on_input", "system_sound", False),
    _SettingRow(_RowKind.NUMBER, "  Delay (seconds)",    "waiting_on_input", "delay_seconds", 10),
]
# fmt: on

# Pre-compute the indices of interactive (non-HEADER) rows for navigation
_INTERACTIVE_INDICES = [i for i, r in enumerate(ROWS) if r.kind != _RowKind.HEADER]


class NotificationSettings(ModalScreen[dict | None]):
    """Notification settings with manual Up/Down/Tab/Enter navigation."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("up", "move_up", show=False),
        Binding("down", "move_down", show=False),
        Binding("tab", "toggle_item", show=False),
        Binding("enter", "confirm", show=False),
    ]

    DEFAULT_CSS = """
    NotificationSettings {
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
        width: 22;
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
        self._nav_pos = 0  # index into _INTERACTIVE_INDICES

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Static("Notification Settings", id="settings-title")
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
                            id=f"input-{row.key}",
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
        if row.category is None:
            return self._current.get(row.key, row.default)
        return self._current.get(row.category, {}).get(row.key, row.default)

    def _set_value(self, row: _SettingRow, value) -> None:
        if row.category is None:
            self._current[row.key] = value
        else:
            self._current.setdefault(row.category, {})[row.key] = value

    def _update_focus(self) -> None:
        row = ROWS[_INTERACTIVE_INDICES[self._nav_pos]]
        if row.kind == _RowKind.NUMBER:
            self.query_one(f"#input-{row.key}", Input).focus()
        else:
            self.set_focus(None)

    def _render_all(self) -> None:
        selected_row_idx = _INTERACTIVE_INDICES[self._nav_pos]
        for i, row in enumerate(ROWS):
            is_selected = i == selected_row_idx
            widget = self.query_one(f"#row-{i}")

            if row.kind == _RowKind.HEADER:
                continue  # headers don't change

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
        # Read numeric inputs and validate
        try:
            minutes = float(self.query_one("#input-long_turn_minutes", Input).value)
        except ValueError:
            minutes = 5.0
        try:
            delay = float(self.query_one("#input-delay_seconds", Input).value)
        except ValueError:
            delay = 10.0

        result = _deep_copy(self._current)
        result.setdefault("long_turn_completion", {})["long_turn_minutes"] = max(
            0.1, minutes
        )
        result.setdefault("waiting_on_input", {})["delay_seconds"] = max(1, delay)
        self.dismiss(result)


def _deep_copy(d: dict) -> dict:
    """Shallow-ish copy sufficient for our two-level nested config."""
    out = dict(d)
    for k, v in out.items():
        if isinstance(v, dict):
            out[k] = dict(v)
    return out
