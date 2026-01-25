"""Modal text input dialog with path autocomplete."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class InputDialog(ModalScreen[str | None]):
    """Modal with a text input and directory suggestions. Returns the path or None."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("tab", "autocomplete", "Autocomplete", show=False),
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
    #suggestions {
        color: $text-muted;
        margin-top: 0;
        max-height: 5;
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
        self._current_suggestions: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="input-dialog"):
            yield Static(self._label, id="input-label")
            yield Input(value=self._default, id="input-field")
            yield Static("", id="suggestions")
            yield Static(
                "[bold]Tab[/] Autocomplete  [bold]Enter[/] Confirm  [bold]Esc[/] Cancel",
                id="input-hint",
            )

    def on_mount(self) -> None:
        self._update_suggestions(self._default)

    def on_input_changed(self, event: Input.Changed) -> None:
        self._update_suggestions(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_autocomplete(self) -> None:
        if not self._current_suggestions:
            return
        inp = self.query_one("#input-field", Input)
        text = inp.value
        path = Path(text).expanduser()

        if path.is_dir():
            # Complete to first child
            completed = str(Path(text) / self._current_suggestions[0]) + "/"
        else:
            # Complete the partial name
            parent_str = str(Path(text).parent)
            if parent_str == ".":
                completed = self._current_suggestions[0] + "/"
            else:
                completed = parent_str + "/" + self._current_suggestions[0] + "/"

        inp.value = completed
        inp.cursor_position = len(completed)
        self._update_suggestions(completed)

    def _update_suggestions(self, text: str) -> None:
        self._current_suggestions = self._get_suggestions(text)
        widget = self.query_one("#suggestions", Static)
        if self._current_suggestions:
            display = "  ".join(f"{s}/" for s in self._current_suggestions)
            widget.update(display)
        else:
            widget.update("")

    def _get_suggestions(self, text: str) -> list[str]:
        if not text:
            return []
        try:
            path = Path(text).expanduser()
            if path.is_dir():
                return sorted(
                    d.name
                    for d in path.iterdir()
                    if d.is_dir() and not d.name.startswith(".")
                )[:8]
            # Partial name — match siblings
            parent = path.parent
            prefix = path.name
            if parent.is_dir():
                return sorted(
                    d.name
                    for d in parent.iterdir()
                    if d.is_dir()
                    and d.name.startswith(prefix)
                    and not d.name.startswith(".")
                )[:8]
        except (PermissionError, OSError):
            pass
        return []
