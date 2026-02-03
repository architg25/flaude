"""Notification settings dialog — manual navigation, no focusable widgets."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, Input


SETTINGS = [
    ("enabled", "Notifications", True),
    ("terminal_bell", "Terminal bell", True),
    ("macos_alert", "macOS alert", False),
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
    #timer-row {
        padding: 0 1;
        height: 3;
    }
    #timer-row-selected {
        padding: 0 1;
        height: 3;
        background: $primary 30%;
    }
    #input-timer {
        width: 12;
        margin-left: 2;
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
        # 5 items: 4 toggles + 1 timer input
        self._item_count = len(SETTINGS) + 1

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Static("Notification Settings", id="settings-title")
            for i, (key, label, _) in enumerate(SETTINGS):
                yield Static("", id=f"row-{i}", classes="setting-line")
            yield Static("", id="row-timer", classes="setting-line")
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
        # Remove focus from the Input so arrow keys work
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
        # If focused on input, don't let it also bubble
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

        timer_row = self.query_one("#row-timer", Static)
        mins = self._current.get("long_turn_minutes", 5)
        timer_row.update(f"  Timer (minutes)")
        is_timer = self._index == len(SETTINGS)
        timer_row.set_class(is_timer, "setting-line-selected")
        timer_row.set_class(not is_timer, "setting-line")

    def _save(self) -> None:
        try:
            minutes = float(self.query_one("#input-timer", Input).value)
        except ValueError:
            minutes = 5.0
        result = dict(self._current)
        result["long_turn_minutes"] = max(0.1, minutes)
        self.dismiss(result)
