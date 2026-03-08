"""Help dialog showing all keybindings."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


class HelpDialog(ModalScreen[None]):
    """Modal showing all available keybindings."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("question_mark", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    HelpDialog {
        align: center middle;
    }
    #help-dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    #help-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    .help-row {
        margin: 0 1;
    }
    #help-hint {
        margin-top: 1;
        color: $text-muted;
        text-align: center;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static("Keyboard Shortcuts", id="help-title")
            yield Static(
                "[bold]Enter[/] / [bold]g[/]     Go to Session", classes="help-row"
            )
            yield Static(
                "[bold]n[/]             New Claude Session", classes="help-row"
            )
            yield Static(
                "[bold]p[/]             Send Prompt to Session", classes="help-row"
            )
            yield Static("[bold]d[/]             Exit Session", classes="help-row")
            yield Static(
                "[bold]G[/]             Assign Session to Group", classes="help-row"
            )
            yield Static("[bold]Enter[/] on group  Rename Group", classes="help-row")
            yield Static(
                "[bold]s[/]             Toggle Notifications", classes="help-row"
            )
            yield Static("[bold]S[/]             Settings", classes="help-row")
            yield Static(
                "[bold]h[/]             Toggle Hidden Sessions", classes="help-row"
            )
            yield Static("[bold]l[/]             Cycle Log Mode", classes="help-row")
            yield Static("[bold]t[/]             Change Theme", classes="help-row")
            yield Static(
                "[bold]L[/]             Loops Panel (x cancel, X cancel all)",
                classes="help-row",
            )
            yield Static("[bold]?[/]             This Help", classes="help-row")
            yield Static("[bold]q[/]             Quit", classes="help-row")
            yield Static("[bold]Esc[/] Close", id="help-hint")

    def action_close(self) -> None:
        self.dismiss(None)
