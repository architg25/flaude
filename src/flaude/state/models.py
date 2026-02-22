"""Pydantic models for session state."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    NEW = "new"
    WORKING = "working"
    IDLE = "idle"
    WAITING_PERMISSION = "waiting_permission"
    WAITING_ANSWER = "waiting_answer"
    ERROR = "error"
    ENDED = "ended"


# Canonical status indicators — used by all UI surfaces
STATUS_INDICATORS: dict[SessionStatus, str] = {
    SessionStatus.NEW: "◆",
    SessionStatus.WORKING: "▶",
    SessionStatus.IDLE: "●",
    SessionStatus.WAITING_PERMISSION: "⏳",
    SessionStatus.WAITING_ANSWER: "❓",
    SessionStatus.ERROR: "✖",
    SessionStatus.ENDED: "■",
}


class LastTool(BaseModel):
    name: str
    summary: str
    at: datetime


class SessionState(BaseModel):
    model_config = {"extra": "ignore"}

    session_id: str
    status: SessionStatus = SessionStatus.WORKING
    cwd: str = ""
    permission_mode: str = "default"
    started_at: datetime
    last_event: str = ""
    last_event_at: datetime
    transcript_path: str | None = None
    tool_stats: dict[str, int] = Field(default_factory=dict)
    last_tool: LastTool | None = None
    last_prompt: str | None = None
    pending_question: dict | None = None
    terminal: str | None = None
    turn_started_at: datetime | None = None
    last_turn_duration: float = 0
    model: str | None = None
    context_tokens: int = 0
    error_count: int = 0
    subagent_count: int = 0

    @property
    def is_plan_approval(self) -> bool:
        """True when pending_question is a plan approval, not a user question."""
        return bool(self.pending_question and "questions" not in self.pending_question)
