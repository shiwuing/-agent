from __future__ import annotations

import os

from ..models import Action, STATUS_INCOMPLETE, STATUS_TOOL_ERROR
from .prompts import SYSTEM_PROMPT, build_user_prompt


TOOL_SCHEMAS = [
    {
        "name": "search_docs",
        "description": "按查询检索知识库文档片段。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索查询"},
                "top_k": {"type": "integer", "description": "返回片段数量"},
                "reason": {"type": "string", "description": "选择该动作的简要依据"},
            },
            "required": ["query", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_document",
        "description": "读取指定文档或分节的原文。",
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "文档 ID"},
                "section_id": {"type": "string", "description": "分节 ID"},
                "reason": {"type": "string", "description": "选择该动作的简要依据"},
            },
            "required": ["doc_id", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "final_answer",
        "description": "给出最终回答，必须包含引用文档 ID 与原文片段。",
        "input_schema": {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "doc_id": {"type": "string"},
                            "section_id": {"type": "string"},
                            "quote": {"type": "string"},
                        },
                        "required": ["doc_id", "section_id", "quote"],
                        "additionalProperties": False,
                    },
                },
                "reason": {"type": "string", "description": "选择该动作的简要依据"},
            },
            "required": ["answer", "citations", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "ask_user",
        "description": "资料冲突或信息不足时，向用户请求确认或补充信息。",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "conflicts": {"type": "array", "items": {"type": "object"}},
                "gaps": {"type": "array", "items": {"type": "string"}},
                "reason": {"type": "string", "description": "选择该动作的简要依据"},
            },
            "required": ["question", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "report_incomplete",
        "description": "无法完成任务时报告原因与状态。",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["INSUFFICIENT_INFO", "TOOL_ERROR", "INCOMPLETE"],
                },
            },
            "required": ["reason", "status"],
            "additionalProperties": False,
        },
    },
]


class AnthropicLLM:
    provider = "anthropic"

    def __init__(self, model: str | None = None, max_tokens: int = 2048):
        import anthropic  # 延迟导入：Mock 模式无需安装/初始化 SDK

        self.client = anthropic.Anthropic()
        self.model = model or os.getenv("MODEL_ID", "claude-opus-5-5")
        self.max_tokens = max_tokens

    def decide(self, state) -> Action:
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                tools=TOOL_SCHEMAS,
                tool_choice={"type": "auto"},
                messages=[{"role": "user", "content": build_user_prompt(state)}],
            )
        except Exception as exc:  # noqa: BLE001
            return Action(
                type="report_incomplete",
                status=STATUS_TOOL_ERROR,
                reason=f"模型调用失败：{exc}",
            )

        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            return Action(
                type="report_incomplete",
                status=STATUS_TOOL_ERROR,
                reason=f"模型拒绝回答：{details}",
            )

        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                return self._parse(block.name, dict(block.input or {}))

        text = "".join(
            getattr(block, "text", "")
            for block in response.content
            if getattr(block, "type", None) == "text"
        )
        return Action(
            type="report_incomplete",
            status=STATUS_INCOMPLETE,
            reason=f"模型未返回工具调用：{text[:200]}",
        )

    def _parse(self, name: str, payload: dict) -> Action:
        reason = payload.get("reason", "")
        if name == "search_docs":
            return Action(
                type="tool",
                tool="search_docs",
                args={
                    "query": payload.get("query", ""),
                    "top_k": payload.get("top_k", 8),
                },
                reason=reason,
            )
        if name == "read_document":
            args = {"doc_id": payload.get("doc_id", "")}
            if payload.get("section_id"):
                args["section_id"] = payload["section_id"]
            return Action(type="tool", tool="read_document", args=args, reason=reason)
        if name == "final_answer":
            return Action(
                type="answer",
                answer=payload.get("answer", ""),
                citations=payload.get("citations", []),
                reason=reason,
            )
        if name == "ask_user":
            return Action(
                type="ask_user",
                question=payload.get("question", ""),
                conflicts=payload.get("conflicts", []),
                gaps=payload.get("gaps", []),
                reason=reason,
            )
        if name == "report_incomplete":
            return Action(
                type="report_incomplete",
                status=payload.get("status", STATUS_INCOMPLETE),
                reason=payload.get("reason", "模型报告未完成"),
            )
        return Action(
            type="report_incomplete",
            status=STATUS_INCOMPLETE,
            reason=f"未知动作：{name}",
        )
