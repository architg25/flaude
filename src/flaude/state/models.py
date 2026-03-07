"""Pydantic models for session state."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    NEW = "new"
    WORKING = "working"
    IDLE = "idle"
    WAITING_PERMISSION = "waiting_permission"
    WAITING_ANSWER = "waiting_answer"
    PLAN = "plan"
    ERROR = "error"
    ENDED = "ended"


@dataclass(frozen=True, slots=True)
class StatusInfo:
    """Canonical display properties for a session status."""

    label: str
    indicator: str
    theme_var: str
    bold: bool
    sort_priority: int


STATUS_INFO: dict[SessionStatus, StatusInfo] = {
    SessionStatus.NEW: StatusInfo("NEW", "◆", "accent", True, 2),
    SessionStatus.WORKING: StatusInfo("RUNNING", "▶", "success", True, 3),
    SessionStatus.IDLE: StatusInfo("IDLE", "●", "text-muted", False, 4),
    SessionStatus.WAITING_PERMISSION: StatusInfo(
        "PERMISSION", "⏳", "warning", True, 0
    ),
    SessionStatus.WAITING_ANSWER: StatusInfo("INPUT", "❓", "accent", True, 0),
    SessionStatus.PLAN: StatusInfo("PLAN", "📋", "warning", True, 0),
    SessionStatus.ERROR: StatusInfo("ERROR", "✖", "error", True, 1),
    SessionStatus.ENDED: StatusInfo("ENDED", "■", "text-muted", False, 5),
}


WAITING_STATUSES = (
    SessionStatus.WAITING_PERMISSION,
    SessionStatus.WAITING_ANSWER,
    SessionStatus.PLAN,
)


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
    tty: str | None = None
    turn_started_at: datetime | None = None
    last_turn_duration: float = 0
    model: str | None = None
    context_tokens: int = 0
    error_count: int = 0
    subagent_count: int = 0
    team_name: str | None = None
    agent_name: str | None = None
    lead_session_id: str | None = None
    custom_title: str | None = None
    git_repo_root: str | None = None
    git_branch: str | None = None
    git_is_worktree: bool = False
    is_tmux: bool | None = None
    tmux_pane: str | None = None
    parent_terminal: str | None = None
