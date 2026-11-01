from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


STATUS_ANSWERED = "ANSWERED"
STATUS_NEED_CONFIRMATION = "NEED_CONFIRMATION"
STATUS_INSUFFICIENT_INFO = "INSUFFICIENT_INFO"
STATUS_TOOL_ERROR = "TOOL_ERROR"
STATUS_INCOMPLETE = "INCOMPLETE"


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None
    summary: str = ""


@dataclass
class Action:
    type: str
    tool: str | None = None
    args: dict = field(default_factory=dict)
    answer: str = ""
    citations: list[dict] = field(default_factory=list)
    question: str = ""
    conflicts: list[dict] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    reason: str = ""
    status: str | None = None

    def to_trace(self) -> dict:
        payload: dict[str, Any] = {"type": self.type}
        if self.type == "tool":
            payload["tool"] = self.tool
            payload["args"] = self.args
        elif self.type == "answer":
            payload["answer_preview"] = self.answer[:120]
            payload["citations"] = self.citations
        elif self.type == "ask_user":
            payload["question"] = self.question
        elif self.type == "report_incomplete":
            payload["status"] = self.status
        return payload


@dataclass
class Observation:
    step: int
    tool: str
    args: dict
    ok: bool
    summary: str
    data: Any = None
    error: str | None = None

    def to_trace(self) -> dict:
        return {
            "ok": self.ok,
            "summary": self.summary,
            "error": self.error,
            "data": self.data,
        }


@dataclass
class AgentState:
    question: str
    history: list[dict] = field(default_factory=list)
    merged_question: str = ""
    current_query: str = ""
    observations: list[Observation] = field(default_factory=list)
    read_sections: dict[str, dict] = field(default_factory=dict)
    pending_conflict: dict | None = None
    search_attempts: int = 0
    retry_count: dict[str, int] = field(default_factory=dict)
    status: str = "RUNNING"

    def __post_init__(self) -> None:
        if not self.merged_question:
            self.merged_question = self.question
        if not self.current_query:
            self.current_query = self.merged_question
