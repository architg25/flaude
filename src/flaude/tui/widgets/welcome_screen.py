"""Welcome screen shown when no sessions are active."""

from textual.app import ComposeResult
from textual.containers import Center, Middle
from textual.widget import Widget
from textual.widgets import Static

from flaude import __version__

# Logo is 42 chars wide (longest line)
_LOGO_WIDTH = 42

LOGO_LINES = [
    r"    __ _                 _          ",
    r"   / _| | __ _ _   _  __| | ___     ",
    r"  | |_| |/ _` | | | |/ _` |/ _ \    ",
    r"  |  _| | (_| | |_| | (_| |  __/    ",
    r"  |_| |_|\__,_|\__,_|\__,_|\___|    ",
]


def _build_content() -> str:
    """Build the welcome screen as a single pre-formatted string."""
    lines: list[str] = []

    # Logo
    for line in LOGO_LINES:
        lines.append(f"[bold]{line}[/]")

    # Version right-aligned to logo width
    version = f"v{__version__}"
    lines.append(f"[dim italic]{version:>{_LOGO_WIDTH}}[/]")

    # Tagline
    lines.append("")
    tagline = "claude code session manager"
    pad = (_LOGO_WIDTH - len(tagline)) // 2
    lines.append(f"[dim]{' ' * pad}{tagline}[/]")

    # Actions
    lines.append("")
    lines.append(f"{'':>13}[bold]n[/]  start a new session")
    lines.append(f"{'':>13}[bold]L[/]  loop manager")
    lines.append(f"{'':>13}[bold]S[/]  settings")

    # Tips
    lines.append("")
    tip1 = "existing sessions appear automatically when hooks fire"
    pad1 = (_LOGO_WIDTH - len(tip1)) // 2
    lines.append(f"[dim italic]{' ' * pad1}{tip1}[/]")
    tip2 = "run flaude init if hooks not set up"
    pad2 = (_LOGO_WIDTH - len(tip2)) // 2
    lines.append(
        f"[dim italic]{' ' * pad2}run [bold]flaude init[/] if hooks not set up[/]"
    )

    return "\n".join(lines)


class WelcomeScreen(Widget):
    """Full-screen welcome shown when no sessions exist."""

    DEFAULT_CSS = """
    WelcomeScreen {
        width: 1fr;
        height: 1fr;
        align: center middle;
    }

    WelcomeScreen #welcome-content {
        width: auto;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(_build_content(), id="welcome-content")
