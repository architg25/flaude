"""Modal text input dialog."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class InputDialog(ModalScreen[str | None]):
    """Modal with a text input. Returns the entered string or None on Esc."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    InputDialog {
        align: center middle;
    }
    #input-dialog {
        width: 70;
        height: auto;
        padding: 1 2;
        border: solid $primary;
        background: $surface;
    }
    #input-label {
        margin-bottom: 1;
    }
    #input-hint {
        margin-top: 1;
        color: $text-muted;
        text-align: center;
    }
    """

    def __init__(self, label: str, default: str = "") -> None:
        super().__init__()
        self._label = label
        self._default = default

    def compose(self) -> ComposeResult:
        with Vertical(id="input-dialog"):
            yield Static(self._label, id="input-label")
            yield Input(value=self._default, id="input-field")
            yield Static("[Enter] Confirm  [Esc] Cancel", id="input-hint")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
