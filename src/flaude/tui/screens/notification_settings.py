"""Notification settings dialog."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Switch, Input, Static, Label, Button


class NotificationSettings(ModalScreen[dict | None]):
    """Modal for configuring notification preferences."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("up", "focus_previous", show=False),
        Binding("down", "focus_next", show=False),
        Binding("tab", "toggle_focused", show=False),
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
    .setting-row {
        height: 3;
        margin: 0 1;
    }
    .setting-row Label {
        width: 20;
        padding-top: 1;
    }
    .setting-row Switch {
        width: auto;
    }
    .setting-row Input {
        width: 10;
    }
    #btn-save {
        margin-top: 1;
        width: 100%;
    }
    #settings-hint {
        margin-top: 1;
        color: $text-muted;
        text-align: center;
    }
    """

    def __init__(self, current: dict) -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        c = self._current
        with Vertical(id="settings-dialog"):
            yield Static("Notification Settings", id="settings-title")
            with Horizontal(classes="setting-row"):
                yield Label("Notifications")
                yield Switch(value=c.get("enabled", True), id="sw-enabled")
            with Horizontal(classes="setting-row"):
                yield Label("Terminal bell")
                yield Switch(value=c.get("terminal_bell", True), id="sw-bell")
            with Horizontal(classes="setting-row"):
                yield Label("macOS alert")
                yield Switch(value=c.get("macos_alert", False), id="sw-macos")
            with Horizontal(classes="setting-row"):
                yield Label("System sound")
                yield Switch(value=c.get("system_sound", False), id="sw-sound")
            with Horizontal(classes="setting-row"):
                yield Label("Timer (minutes)")
                yield Input(
                    value=str(c.get("long_turn_minutes", 5)),
                    id="input-timer",
                    type="number",
                )
            yield Button("Save", id="btn-save", variant="primary")
            yield Static(
                "[bold]Up[/]/[bold]Down[/] Navigate  "
                "[bold]Tab[/] Toggle  "
                "[bold]Esc[/] Cancel",
                id="settings-hint",
            )

    def action_toggle_focused(self) -> None:
        focused = self.focused
        if isinstance(focused, Switch):
            focused.toggle()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            self._save()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Prevent Enter from bubbling to the app
        event.stop()
        self._save()

    def _save(self) -> None:
        try:
            minutes = float(self.query_one("#input-timer", Input).value)
        except ValueError:
            minutes = 5.0
        self.dismiss(
            {
                "enabled": self.query_one("#sw-enabled", Switch).value,
                "terminal_bell": self.query_one("#sw-bell", Switch).value,
                "macos_alert": self.query_one("#sw-macos", Switch).value,
                "system_sound": self.query_one("#sw-sound", Switch).value,
                "long_turn_minutes": max(0.1, minutes),
            }
        )

    def action_cancel(self) -> None:
        self.dismiss(None)
