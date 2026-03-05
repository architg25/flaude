"""Modal text input dialog with path autocomplete and arrow key selection."""

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
        Binding("down", "select_next", show=False),
        Binding("up", "select_prev", show=False),
    ]

    DEFAULT_CSS = """
    InputDialog {
        align: center middle;
    }
    #input-dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        border: round $primary;
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

    def __init__(
        self, label: str, default: str = "", autocomplete: bool = True
    ) -> None:
        super().__init__()
        self._label = label
        self._default = default
        self._autocomplete = autocomplete
        self._current_suggestions: list[str] = []
        self._selected_index: int = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="input-dialog"):
            yield Static(self._label, id="input-label")
            yield Input(value=self._default, id="input-field")
            if self._autocomplete:
                yield Static("", id="suggestions")
                yield Static(
                    "[bold]Tab[/] Autocomplete  "
                    "[bold]Up[/]/[bold]Down[/] Navigate  "
                    "[bold]Enter[/] Confirm  "
                    "[bold]Esc[/] Cancel",
                    id="input-hint",
                )
            else:
                yield Static(
                    "[bold]Enter[/] Confirm  [bold]Esc[/] Cancel",
                    id="input-hint",
                )

    def on_mount(self) -> None:
        if self._autocomplete:
            self._update_suggestions(self._default)

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._autocomplete:
            self._selected_index = 0
            self._update_suggestions(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        # In autocomplete mode, empty = cancel. Otherwise, empty is a valid value.
        self.dismiss(value if (value or not self._autocomplete) else None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_select_next(self) -> None:
        if self._current_suggestions:
            self._selected_index = (self._selected_index + 1) % len(
                self._current_suggestions
            )
            self._render_suggestions()

    def action_select_prev(self) -> None:
        if self._current_suggestions:
            self._selected_index = (self._selected_index - 1) % len(
                self._current_suggestions
            )
            self._render_suggestions()

    def action_autocomplete(self) -> None:
        if self._current_suggestions:
            self._accept_selected()

    def _accept_selected(self) -> None:
        if not self._current_suggestions:
            return
        inp = self.query_one("#input-field", Input)
        text = inp.value
        selected = self._current_suggestions[self._selected_index]
        path = Path(text).expanduser()

        if path.is_dir():
            completed = str(Path(text) / selected) + "/"
        else:
            parent_str = str(Path(text).parent)
            if parent_str == ".":
                completed = selected + "/"
            else:
                completed = parent_str + "/" + selected + "/"

        inp.value = completed
        inp.cursor_position = len(completed)
        self._selected_index = 0
        self._update_suggestions(completed)

    def _update_suggestions(self, text: str) -> None:
        self._current_suggestions = self._get_suggestions(text)
        if self._selected_index >= len(self._current_suggestions):
            self._selected_index = 0
        self._render_suggestions()

    def _render_suggestions(self) -> None:
        widget = self.query_one("#suggestions", Static)
        if not self._current_suggestions:
            widget.update("")
            return
        parts = []
        for i, name in enumerate(self._current_suggestions):
            if i == self._selected_index:
                parts.append(f"[bold reverse] {name}/ [/]")
            else:
                parts.append(f"{name}/")
        widget.update("  ".join(parts))

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
