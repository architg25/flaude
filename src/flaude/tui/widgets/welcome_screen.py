"""Welcome screen shown when no sessions are active."""

from textual.app import ComposeResult
from textual.containers import Center, Middle
from textual.widget import Widget
from textual.widgets import Static

from flaude import __version__

LOGO = r"""
        __ _                 _
       / _| | __ _ _   _  __| | ___
      | |_| |/ _` | | | |/ _` |/ _ \
      |  _| | (_| | |_| | (_| |  __/
      |_| |_|\__,_|\__,_|\__,_|\___|"""


class WelcomeScreen(Widget):
    """Full-screen welcome shown when no sessions exist."""

    DEFAULT_CSS = """
    WelcomeScreen {
        width: 1fr;
        height: 1fr;
    }

    WelcomeScreen #welcome-middle {
        width: 1fr;
        height: 1fr;
    }

    WelcomeScreen #welcome-center {
        width: auto;
    }

    WelcomeScreen #welcome-logo {
        color: $text;
        text-style: bold;
        width: auto;
    }

    WelcomeScreen #welcome-version {
        color: $text-muted;
        text-style: italic;
        text-align: right;
        width: auto;
        margin: 0 0 1 0;
    }

    WelcomeScreen .welcome-action {
        width: auto;
        margin: 0 0 0 6;
    }

    WelcomeScreen .welcome-key {
        color: $primary;
        text-style: bold;
        width: auto;
    }

    WelcomeScreen #welcome-tips {
        color: $text-muted;
        text-style: italic;
        width: auto;
        margin: 1 0 0 6;
    }
    """

    def compose(self) -> ComposeResult:
        with Middle(id="welcome-middle"):
            with Center(id="welcome-center"):
                yield Static(LOGO, id="welcome-logo")
                yield Static(f"v{__version__}", id="welcome-version")
                yield Static(
                    "  [bold]n[/]  start a new session",
                    classes="welcome-action",
                )
                yield Static(
                    "  [bold]L[/]  loop manager",
                    classes="welcome-action",
                )
                yield Static(
                    "  [bold]S[/]  settings",
                    classes="welcome-action",
                )
                yield Static(
                    "existing sessions appear automatically\n"
                    "run [bold]flaude init[/] if hooks not set up",
                    id="welcome-tips",
                )
