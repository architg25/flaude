"""Simple yes/no confirmation dialog."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


class ConfirmDialog(ModalScreen[bool]):
    """Modal confirmation dialog. Returns True (y) or False (n/Esc)."""

    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    ConfirmDialog {
        align: center middle;
    }
    #confirm-dialog {
        width: 50;
        height: auto;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    #confirm-message {
        margin-bottom: 1;
    }
    #confirm-hint {
        color: $text-muted;
        text-align: center;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(self._message, id="confirm-message")
            yield Static(
                "[bold]y[/] Yes  [bold]n[/] No  [bold]Esc[/] Cancel", id="confirm-hint"
            )

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
