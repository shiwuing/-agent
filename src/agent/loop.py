from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..citation import validate_citations
from ..kb import normalize
from ..models import (
    AgentState,
    Observation,
    STATUS_ANSWERED,
    STATUS_INCOMPLETE,
    STATUS_NEED_CONFIRMATION,
)
from ..trace import TraceWriter
from .context import merge_history


class AgentLoop:
    """ReAct 主循环：模型决策 -> 执行工具 -> 观察结果 -> 继续决策或结束。"""

    def __init__(self, kb, llm, runtime, max_steps: int = 8, trace_path=None):
        self.kb = kb
        self.llm = llm
        self.runtime = runtime
        self.max_steps = max_steps
        self.trace_path = trace_path

    def run(self, question: str, history: list[dict] | None = None) -> dict:
        history = history or []
        merged = merge_history(question, history)
        state = AgentState(
            question=question,
            history=history,
            merged_question=merged,
            current_query=merged,
        )
        run_id = (
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
            f"{uuid.uuid4().hex[:6]}"
        )
        trace = TraceWriter(self.trace_path or "trace.jsonl")
        final: dict | None = None

        for step in range(1, self.max_steps + 1):
            action = self.llm.decide(state)

            if action.type == "tool":
                result = self.runtime.call(action.tool, action.args)
                observation = Observation(
                    step=step,
                    tool=action.tool,
                    args=action.args,
                    ok=result.ok,
                    summary=result.summary,
                    data=result.data,
                    error=result.error,
                )
                state.observations.append(observation)
                if result.ok:
                    self._remember(state, action, result.data)
                trace.log(step, action, observation, action.reason)
                continue

            if action.type == "answer":
                valid, errors = validate_citations(
                    action.answer,
                    action.citations,
                    self.kb,
                    observed_sections=self._observed_sections(state),
                )
                if valid:
                    observation = Observation(
                        step=step, tool="answer", args={}, ok=True,
                        summary="引用校验通过，给出回答",
                        data={"citations": action.citations},
                    )
                    final = self._final(
                        run_id, state, STATUS_ANSWERED,
                        answer=action.answer, citations=action.citations,
                    )
                else:
                    observation = Observation(
                        step=step, tool="answer", args={}, ok=False,
                        summary="引用校验失败，降级为待确认",
                        data={"errors": errors},
                    )
                    final = self._final(
                        run_id, state, STATUS_NEED_CONFIRMATION,
                        answer="", gaps=errors,
                    )
                trace.log(step, action, observation, action.reason)
                break

            if action.type == "ask_user":
                observation = Observation(
                    step=step, tool="ask_user", args={}, ok=True,
                    summary="冲突无法裁决，请求用户确认",
                    data={"question": action.question, "conflicts": action.conflicts},
                )
                final = self._final(
                    run_id, state, STATUS_NEED_CONFIRMATION,
                    answer=action.question, conflicts=action.conflicts, gaps=action.gaps,
                    citations=self._conflict_citations(action.conflicts),
                )
                trace.log(step, action, observation, action.reason)
                break

            if action.type == "report_incomplete":
                status = action.status or STATUS_INCOMPLETE
                observation = Observation(
                    step=step, tool="report_incomplete", args={}, ok=False,
                    summary=action.reason, data={"status": status},
                )
                final = self._final(
                    run_id, state, status, answer="", gaps=[action.reason],
                )
                trace.log(step, action, observation, action.reason)
                break

        if final is None:
            final = self._final(
                run_id, state, STATUS_INCOMPLETE, answer="",
                gaps=[f"达到步数上限 {self.max_steps}，任务未完成"],
            )

        final["steps"] = len(trace.entries)
        final["tool_calls"] = len(state.observations)
        final["trace_file"] = self._display_trace_path()
        trace.write(final)
        return final

    def _display_trace_path(self) -> str | None:
        if not self.trace_path:
            return None
        path = Path(self.trace_path)
        try:
            return str(path.resolve().relative_to(Path.cwd().resolve())).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    def _conflict_citations(self, conflicts: list[dict]) -> list[dict]:
        """把冲突项里的逐字原文同时写入 citations，便于统一校验。"""
        citations: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for conflict in conflicts or []:
            if not isinstance(conflict, dict):
                continue
            if conflict.get("doc_id"):
                items = [conflict]
            else:
                items = conflict.get("items") or conflict.get("conflicts") or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                doc_id = item.get("doc_id")
                section_id = item.get("section_id")
                quote = item.get("quote") or ""
                key = (doc_id, section_id)
                if not doc_id or not section_id or not quote or key in seen:
                    continue
                section = self.kb.get_section(doc_id, section_id)
                if section is None:
                    continue
                if normalize(quote) not in normalize(section["content"]):
                    continue
                citations.append({
                    "doc_id": doc_id,
                    "section_id": section_id,
                    "quote": quote,
                })
                seen.add(key)
        return citations

    def _observed_sections(self, state: AgentState) -> list[dict]:
        """汇总本轮工具实际返回过的分节，供引用校验判断对比性数值。"""
        seen: dict[tuple[str, str], dict] = {}
        for observation in state.observations:
            data = observation.data
            if not isinstance(data, dict):
                continue
            hits = data.get("hits")
            if isinstance(hits, list):
                for hit in hits:
                    if (
                        isinstance(hit, dict)
                        and hit.get("doc_id")
                        and hit.get("content")
                    ):
                        seen[(hit["doc_id"], hit.get("section_id", ""))] = hit
            elif data.get("doc_id") and data.get("content"):
                seen[(data["doc_id"], data.get("section_id", ""))] = data
        return list(seen.values())

    def _remember(self, state: AgentState, action, data) -> None:
        if action.tool == "search_docs" and isinstance(data, dict):
            state.pending_conflict = data.get("conflict_hint")
        elif (
            action.tool == "read_document"
            and isinstance(data, dict)
            and "section_id" in data
        ):
            identity = f"{data['doc_id']}:{data['section_id']}"
            state.read_sections[identity] = data

    def _final(
        self,
        run_id: str,
        state: AgentState,
        status: str,
        answer: str = "",
        citations: list[dict] | None = None,
        gaps: list[str] | None = None,
        conflicts: list[dict] | None = None,
    ) -> dict:
        return {
            "run_id": run_id,
            "question": state.question,
            "merged_question": state.merged_question,
            "status": status,
            "answer": answer,
            "citations": citations or [],
            "gaps": gaps or [],
            "conflicts": conflicts or [],
            "provider": getattr(self.llm, "provider", "unknown"),
            "model": getattr(self.llm, "model", None),
            "retrieval_mode": getattr(self.kb, "retrieval_mode", "keyword"),
            "steps": len(state.observations),
            "tool_calls": len(state.observations),
            "trace_file": self._display_trace_path(),
        }
