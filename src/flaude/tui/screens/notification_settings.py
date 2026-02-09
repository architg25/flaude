"""Notification settings dialog — manual navigation."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Input


SETTINGS = [
    ("enabled", "Notify on finish", False),
    ("terminal_bell", "Terminal bell", True),
    ("macos_alert", "macOS notification", False),
    ("system_sound", "System sound", False),
]


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
        width: 50;
        height: auto;
        padding: 1 2;
        border: solid $primary;
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
    .timer-row {
        height: 3;
        padding: 0 1;
    }
    .timer-row-selected {
        height: 3;
        padding: 0 1;
        background: $primary 30%;
    }
    #timer-label {
        width: 22;
        padding-top: 1;
    }
    #input-timer {
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
        self._current = dict(current)
        self._index = 0
        self._item_count = len(SETTINGS) + 1

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Static("Notification Settings", id="settings-title")
            yield Static(
                "[dim]Alert when a turn finishes after exceeding the timer[/]",
                classes="setting-line",
            )
            for i, (key, label, _) in enumerate(SETTINGS):
                yield Static("", id=f"row-{i}", classes="setting-line")
            with Horizontal(id="timer-container", classes="timer-row"):
                yield Static("  Timer (minutes)", id="timer-label")
                yield Input(
                    value=str(self._current.get("long_turn_minutes", 5)),
                    id="input-timer",
                    type="number",
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

    def action_move_up(self) -> None:
        self._index = (self._index - 1) % self._item_count
        self._render_all()
        self._update_focus()

    def action_move_down(self) -> None:
        self._index = (self._index + 1) % self._item_count
        self._render_all()
        self._update_focus()

    def action_toggle_item(self) -> None:
        if self._index < len(SETTINGS):
            key = SETTINGS[self._index][0]
            self._current[key] = not self._current.get(key, SETTINGS[self._index][2])
            self._render_all()

    def action_confirm(self) -> None:
        self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _update_focus(self) -> None:
        if self._index == len(SETTINGS):
            self.query_one("#input-timer", Input).focus()
        else:
            self.set_focus(None)

    def _render_all(self) -> None:
        for i, (key, label, default) in enumerate(SETTINGS):
            row = self.query_one(f"#row-{i}", Static)
            val = self._current.get(key, default)
            check = "[bold green]ON[/]" if val else "[dim]OFF[/]"
            row.update(f"  {label:<20} {check}")
            row.set_class(i == self._index, "setting-line-selected")
            row.set_class(i != self._index, "setting-line")

        is_timer = self._index == len(SETTINGS)
        container = self.query_one("#timer-container")
        container.set_class(is_timer, "timer-row-selected")
        container.set_class(not is_timer, "timer-row")

    def _save(self) -> None:
        try:
            minutes = float(self.query_one("#input-timer", Input).value)
        except ValueError:
            minutes = 5.0
        result = dict(self._current)
        result["long_turn_minutes"] = max(0.1, minutes)
        self.dismiss(result)
