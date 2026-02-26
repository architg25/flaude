"""Notification manager — alert tracking, firing, and lifecycle.

Tracks which sessions have already been alerted to avoid duplicate
notifications. Handles two categories:
  1. Long turn completion — fires when a turn finishes after exceeding
     a time threshold (e.g., 5 minutes).
  2. Waiting on input — fires after a session has been waiting for user
     input (permission, answer, plan review) for a configurable delay.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable

from flaude.constants import utcnow
from flaude.formatting import format_duration_seconds
from flaude.state.models import SessionState, SessionStatus, WAITING_STATUSES

_WAITING_LABELS = {
    SessionStatus.WAITING_PERMISSION: "Needs permission",
    SessionStatus.WAITING_ANSWER: "Needs your answer",
    SessionStatus.PLAN: "Plan review needed",
}


class NotificationManager:
    """Manages notification state and alert firing for the TUI.

    Separated from FlaudeApp so the logic is testable and the app class
    stays focused on layout and keybindings.
    """

    def __init__(self, bell: Callable[[], None] | None = None) -> None:
        self._alerted_turns: set[str] = set()
        self._alerted_waiting: set[str] = set()
        self._waiting_entered_at: dict[str, datetime] = {}
        self._bell = bell  # app.bell callback for terminal bell

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        active: dict[str, SessionState],
        config: dict,
    ) -> None:
        """Run notification checks for all active sessions.

        Call this every refresh tick. Only fires alerts when notifications
        are enabled in config.
        """
        if not config.get("enabled", False):
            return

        ltc = config.get("long_turn_completion", {})
        woi = config.get("waiting_on_input", {})

        if ltc.get("enabled", True):
            self._check_long_turns(active, ltc)

        if woi.get("enabled", False):
            self._check_waiting(active, woi)

        self._prune(active)

    def seed(
        self,
        active: dict[str, SessionState],
        config: dict,
    ) -> None:
        """Pre-populate alerted sets so existing sessions don't fire.

        Call this when:
        - App starts with notifications already enabled
        - User enables notifications (toggle or settings dialog)
        """
        self.clear()
        ltc = config.get("long_turn_completion", {})
        threshold = ltc.get("long_turn_minutes", 5) * 60
        for sid, state in active.items():
            if state.status == SessionStatus.ENDED:
                continue
            if state.last_turn_duration > threshold and state.turn_started_at is None:
                self._alerted_turns.add(sid)
            if state.status in WAITING_STATUSES:
                self._alerted_waiting.add(sid)

    def clear(self) -> None:
        """Reset all tracking state."""
        self._alerted_turns.clear()
        self._alerted_waiting.clear()
        self._waiting_entered_at.clear()

    # ------------------------------------------------------------------
    # Category 1: Long turn completion
    # ------------------------------------------------------------------

    def _check_long_turns(self, active: dict[str, SessionState], cfg: dict) -> None:
        threshold = cfg.get("long_turn_minutes", 5) * 60
        for sid, state in active.items():
            if (
                state.last_turn_duration > threshold
                and state.turn_started_at is None
                and sid not in self._alerted_turns
            ):
                self._fire_long_turn(state, cfg)
                self._alerted_turns.add(sid)
            # Reset when a new turn starts so it can fire again later
            if state.turn_started_at is not None:
                self._alerted_turns.discard(sid)

    def _fire_long_turn(self, state: SessionState, cfg: dict) -> None:
        project = Path(state.cwd).name if state.cwd else state.session_id[:8]
        duration = format_duration_seconds(state.last_turn_duration)
        body = (state.last_prompt or "")[:80]
        self._fire(cfg, f"Flaude — {project}", f"Finished in {duration}", body)

    # ------------------------------------------------------------------
    # Category 2: Waiting on input
    # ------------------------------------------------------------------

    def _check_waiting(self, active: dict[str, SessionState], cfg: dict) -> None:
        delay = cfg.get("delay_seconds", 10)
        now = utcnow()
        for sid, state in active.items():
            is_waiting = state.status in WAITING_STATUSES
            if is_waiting and sid not in self._alerted_waiting:
                if sid not in self._waiting_entered_at:
                    self._waiting_entered_at[sid] = now
                elif (now - self._waiting_entered_at[sid]).total_seconds() >= delay:
                    self._fire_waiting(state, cfg)
                    self._alerted_waiting.add(sid)
            elif not is_waiting:
                self._alerted_waiting.discard(sid)
                self._waiting_entered_at.pop(sid, None)

    def _fire_waiting(self, state: SessionState, cfg: dict) -> None:
        project = Path(state.cwd).name if state.cwd else state.session_id[:8]
        subtitle = _WAITING_LABELS.get(state.status, "Waiting for input")
        body = ""
        if state.pending_question:
            questions = state.pending_question.get("questions", [])
            if questions:
                body = questions[0].get("question", "")[:80]
        self._fire(cfg, f"Flaude — {project}", subtitle, body)

    # ------------------------------------------------------------------
    # Mechanism dispatch
    # ------------------------------------------------------------------

    def _fire(self, cfg: dict, title: str, subtitle: str, body: str) -> None:
        if cfg.get("terminal_bell", True) and self._bell:
            self._bell()
        if cfg.get("system_sound", False):
            subprocess.Popen(
                ["afplay", "/System/Library/Sounds/Glass.aiff"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        if cfg.get("macos_alert", False):
            safe_body = body.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.Popen(
                [
                    "osascript",
                    "-e",
                    f'display notification "{safe_body}" '
                    f'with title "{title}" subtitle "{subtitle}"',
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------

    def _prune(self, active: dict[str, SessionState]) -> None:
        """Remove ended sessions from tracking sets."""
        active_keys = set(active.keys())
        self._alerted_turns &= active_keys
        self._alerted_waiting &= active_keys
        for sid in list(self._waiting_entered_at):
            if sid not in active_keys:
                del self._waiting_entered_at[sid]
