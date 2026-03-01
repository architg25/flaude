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

    class TogglePlanMode(Message):
        pass

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
        if event.key == "shift+tab":
            event.stop()
            event.prevent_default()
            self.post_message(self.TogglePlanMode())
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

    _HINT_BASE = "[bold]Enter[/] Send  [bold]⇧Enter[/] New Line  "
    _HINT_PLAN_OFF = "[bold]⇧Tab[/] Plan Mode"
    _HINT_PLAN_ON = "[bold]⇧Tab[/] [green]Plan Mode ✓[/]"
    _HINT_TAIL = "  [bold]Esc[/] Cancel"

    def __init__(self, label: str) -> None:
        super().__init__()
        self._label = label
        self._plan_mode = False

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-dialog"):
            yield Static(self._label, id="prompt-label")
            yield PromptTextArea(id="prompt-field")
            yield Static(self._hint_text(), id="prompt-hint")

    def _hint_text(self) -> str:
        plan = self._HINT_PLAN_ON if self._plan_mode else self._HINT_PLAN_OFF
        return self._HINT_BASE + plan + self._HINT_TAIL

    def _refresh_hint(self) -> None:
        self.query_one("#prompt-hint", Static).update(self._hint_text())

    def on_mount(self) -> None:
        self.query_one("#prompt-field").focus()

    def on_prompt_text_area_toggle_plan_mode(
        self, event: PromptTextArea.TogglePlanMode
    ) -> None:
        self._plan_mode = not self._plan_mode
        self._refresh_hint()

    def on_prompt_text_area_submitted(self, event: PromptTextArea.Submitted) -> None:
        text = event.text.strip() or None
        if text and self._plan_mode:
            text = f"/plan\n{text}"
        self.dismiss(text)

    def action_cancel(self) -> None:
        self.dismiss(None)
