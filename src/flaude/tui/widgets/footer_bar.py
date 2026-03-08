"""Custom minimal footer bar with styled keybindings."""

from textual.widgets import Static


# (key, description) pairs — order matters
BINDINGS_LEFT = [
    ("g", "goto"),
    ("n", "new"),
    ("p", "prompt"),
    ("d", "exit"),
    ("l", "log"),
    ("h", "hidden"),
]

BINDINGS_RIGHT = [
    ("S", "settings"),
    ("L", "loops"),
    ("?", "help"),
    ("q", "quit"),
]


class FooterBar(Static):
    """Single-line footer with styled key hints and notification indicator."""

    DEFAULT_CSS = """
    FooterBar {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        self._notif_enabled = False
        super().__init__(self._build_content(), **kwargs)

    def set_notifications(self, enabled: bool) -> None:
        if enabled != self._notif_enabled:
            self._notif_enabled = enabled
            self.update(self._build_content())

    def _build_content(self) -> str:
        parts: list[str] = []

        for key, desc in BINDINGS_LEFT:
            parts.append(f"[$primary bold]{key}[/] [dim]{desc}[/]")

        # Notification toggle with state indicator
        if self._notif_enabled:
            parts.append(f"[$primary bold]s[/] [dim]notif[/] [$success]●[/]")
        else:
            parts.append(f"[$primary bold]s[/] [dim]notif[/] [dim]○[/]")

        for key, desc in BINDINGS_RIGHT:
            parts.append(f"[$primary bold]{key}[/] [dim]{desc}[/]")

        return "  ".join(parts)
