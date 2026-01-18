"""Simple y/n confirmation screen."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Middle
from textual.screen import ModalScreen
from textual.widgets import Static


class ConfirmScreen(ModalScreen[bool]):
    """Modal confirmation dialog. Returns True (y) or False (n/Esc)."""

    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm-dialog {
        width: 50;
        height: auto;
        padding: 1 2;
        border: solid $warning;
        background: $surface;
    }
    #confirm-prompt {
        text-align: center;
        margin-bottom: 1;
    }
    #confirm-hint {
        text-align: center;
        color: $text-muted;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                yield Static(self._message, id="confirm-prompt")
                yield Static("[y] Yes  [n] No", id="confirm-hint")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
