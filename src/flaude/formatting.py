"""Shared formatting utilities for uptime, tokens, and durations."""

from datetime import datetime


def format_uptime(now: datetime, started: datetime) -> str:
    """Format a duration as a human-readable string (e.g., '5m', '2h30m', '1d3h')."""
    delta = now - started
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h{minutes % 60}m"
    days = hours // 24
    return f"{days}d{hours % 24}h"


def format_compact_duration(now: datetime, since: datetime) -> str:
    """Format a duration with seconds precision (e.g., '5s', '3m05s', '1h30m')."""
    secs = max(0, int((now - since).total_seconds()))
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m{secs % 60:02d}s"
    hours = mins // 60
    return f"{hours}h{mins % 60:02d}m"


def format_duration_seconds(seconds: float) -> str:
    """Format a duration in seconds as 'Xm' or 'XhYm'."""
    mins = int(seconds // 60)
    if mins < 60:
        return f"{mins}m"
    return f"{mins // 60}h{mins % 60}m"


def format_token_count(tokens: int) -> str:
    """Format a token count as a human-readable string (e.g., '269K', '1.0M')."""
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{tokens // 1_000}K"
    return str(tokens)
