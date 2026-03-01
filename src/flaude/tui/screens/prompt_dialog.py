"""Modal multi-line input for sending a prompt to a Claude session."""

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea


class PromptTextArea(TextArea):
    """TextArea where Enter submits and Shift+Enter (ctrl+j) inserts a newline.

    TextArea._on_key hardcodes "enter" -> newline insertion, so we
    override it to intercept Enter before that happens.
    """

    class Submitted(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.Submitted(self.text))
            return
        if event.key == "ctrl+j":
            event.stop()
            event.prevent_default()
            start, end = self.selection
            self._replace_via_keyboard("\n", start, end)
            return
        await super()._on_key(event)


class PromptDialog(ModalScreen[str | None]):
    """Multi-line prompt input. Returns the trimmed text or None on cancel."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
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
            yield PromptTextArea(id="prompt-field")
            yield Static(
                "[bold]Enter[/] Send  [bold]Shift+Enter[/] New Line  [bold]Esc[/] Cancel",
                id="prompt-hint",
            )

    def on_mount(self) -> None:
        self.query_one("#prompt-field").focus()

    def on_prompt_text_area_submitted(self, event: PromptTextArea.Submitted) -> None:
        self.dismiss(event.text.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
