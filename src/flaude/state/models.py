"""Pydantic models for session state."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class SessionStatus(str, Enum):
    WORKING = "working"
    IDLE = "idle"
    WAITING_PERMISSION = "waiting_permission"
    WAITING_ANSWER = "waiting_answer"
    ERROR = "error"
    ENDED = "ended"


class PendingPermission(BaseModel):
    request_id: str
    tool_name: str
    tool_input: dict
    rule_matched: str | None = None
    created_at: datetime
    timeout_at: datetime


class LastTool(BaseModel):
    name: str
    summary: str
    at: datetime


class SessionState(BaseModel):
    session_id: str
    status: SessionStatus = SessionStatus.WORKING
    cwd: str = ""
    permission_mode: str = "default"
    started_at: datetime
    last_event: str = ""
    last_event_at: datetime
    transcript_path: str | None = None
    tool_stats: dict[str, int] = {}
    last_tool: LastTool | None = None
    pending_permissions: list[PendingPermission] = []
    pending_question: dict | None = None
    terminal: str | None = None
    error_count: int = 0
    subagent_count: int = 0
