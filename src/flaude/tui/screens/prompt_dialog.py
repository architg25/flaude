"""Modal multi-line input for sending a prompt to a Claude session."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea


class PromptDialog(ModalScreen[str | None]):
    """Multi-line prompt input. Returns the trimmed text or None on cancel."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("tab", "submit", "Send", show=False),
    ]

    DEFAULT_CSS = """
    PromptDialog {
        align: center middle;
    }
    #prompt-dialog {
        width: 80;
        height: auto;
        max-height: 24;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    #prompt-label {
        margin-bottom: 1;
    }
    #prompt-field {
        height: 6;
    }
    #prompt-hint {
        margin-top: 1;
        color: $text-muted;
        text-align: center;
    }
    """

    def __init__(self, label: str) -> None:
        super().__init__()
        self._label = label

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-dialog"):
            yield Static(self._label, id="prompt-label")
            yield TextArea(id="prompt-field")
            yield Static(
                "[bold]Tab[/] Send  [bold]Enter[/] New Line  [bold]Esc[/] Cancel",
                id="prompt-hint",
            )

    def action_submit(self) -> None:
        text = self.query_one("#prompt-field", TextArea).text.strip()
        self.dismiss(text or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
