"""Shared tool-input summarization for hooks and TUI widgets."""

from pathlib import Path


def trunc(s: str, n: int) -> str:
    """Truncate string to n chars, appending '...' if truncated."""
    return s[:n] + ("..." if len(s) > n else "")


def basename(path: str) -> str:
    """Extract filename from a path string."""
    return Path(path).name if path else ""


_SUMMARIZERS: dict[str, object] = {
    "Bash": lambda inp: trunc(inp.get("command", ""), 80),
    "Edit": lambda inp: basename(inp.get("file_path", "")),
    "MultiEdit": lambda inp: basename(inp.get("file_path", "")),
    "Write": lambda inp: basename(inp.get("file_path", "")),
    "Read": lambda inp: basename(inp.get("file_path", "")),
    "Grep": lambda inp: trunc(inp.get("pattern", ""), 40),
    "Glob": lambda inp: inp.get("pattern", ""),
    "Task": lambda inp: trunc(inp.get("prompt", ""), 60),
    "WebFetch": lambda inp: trunc(inp.get("url", ""), 60),
    "CronCreate": lambda inp: f'{inp.get("cron", "")} {trunc(inp.get("prompt", ""), 50)}'.strip(),
    "CronDelete": lambda inp: inp.get("id", ""),
}


def summarize_tool(tool_name: str, tool_input: dict) -> str:
    """Return a short summary of a tool invocation for display."""
    fn = _SUMMARIZERS.get(tool_name)
    if fn:
        return fn(tool_input)
    return tool_name
