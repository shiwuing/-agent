from __future__ import annotations

import re

from ..conflict import detect_conflicts, resolve_conflict
from ..kb import tokenize
from ..models import (
    Action,
    AgentState,
    STATUS_INCOMPLETE,
    STATUS_INSUFFICIENT_INFO,
    STATUS_TOOL_ERROR,
)
from .context import rewrite_query


SPECIFIC_TOKEN_RE = re.compile(
    r"(?=[a-z0-9]*\d)(?=[a-z0-9]*[a-z])[a-z0-9]{2,}"
)
DOC_ID_RE = re.compile(r"^d\d+$")
GAP_SCENARIO_TERMS = (
    "丢了", "丢失", "补开", "作废", "过期", "没盖章", "损坏",
)


class MockLLM:
    """离线 Mock：根据当前观察结果决定下一步动作。

    只用于验证流程、状态机与护栏，不证明真实模型的决策质量。
    """

    provider = "mock"
    model = "mock-policy"

    def __init__(self, kb):
        self.kb = kb
        self.synonyms = kb.synonyms

    def decide(self, state: AgentState) -> Action:
        if not state.observations:
            return self._search(state, state.current_query, "首轮检索")

        last = state.observations[-1]
        if last.tool == "search_docs":
            return self._after_search(state, last)
        if last.tool == "read_document":
            return self._after_read(state, last)
        return Action(
            type="report_incomplete",
            status=STATUS_INCOMPLETE,
            reason="未知观察类型，停止执行",
        )

    def _search(self, state: AgentState, query: str, reason: str) -> Action:
        state.search_attempts += 1
        return Action(
            type="tool",
            tool="search_docs",
            args={"query": query, "top_k": 8},
            reason=reason,
        )

    def _read(self, item: dict, reason: str) -> Action:
        return Action(
            type="tool",
            tool="read_document",
            args={"doc_id": item["doc_id"], "section_id": item["section_id"]},
            reason=reason,
        )

    def _after_search(self, state: AgentState, last) -> Action:
        if not last.ok:
            return self._retry_or_fail(state, last)

        data = last.data or {}
        hits = self._filter_specific(data.get("hits", []), state.merged_question)
        hits = self._filter_exceptions(hits, state.merged_question)
        if not hits:
            if state.search_attempts < 3:
                new_query = rewrite_query(
                    state.current_query, self.synonyms, state.search_attempts
                )
                state.current_query = new_query
                return self._search(
                    state,
                    new_query,
                    f"检索无结果，改写查询（第 {state.search_attempts} 次）",
                )
            return Action(
                type="report_incomplete",
                status=STATUS_INSUFFICIENT_INFO,
                reason="多次改写检索均未命中，知识库中无相关资料",
            )

        hint = data.get("conflict_hint")
        state.pending_conflict = hint
        if hint:
            unread = self._next_unread(state, hint)
            if unread:
                return self._read(unread, "检索提示同一字段数值不一致，读取原文核实")
            return self._resolve_or_ask(state, hint)

        top = hits[0]
        identity = f"{top['doc_id']}:{top['section_id']}"
        if identity not in state.read_sections:
            return self._read(top, "命中高相关片段，读取原文后回答")
        return self._answer_from_hit(top, "已读取相关片段，引用原文回答")

    def _after_read(self, state: AgentState, last) -> Action:
        if not last.ok:
            return self._retry_or_fail(state, last)

        hint = state.pending_conflict
        if hint:
            unread = self._next_unread(state, hint)
            if unread:
                return self._read(unread, "继续读取冲突涉及的其他文档")
            return self._resolve_or_ask(state, hint)

        conflict = detect_conflicts(
            list(state.read_sections.values()), query=state.merged_question
        )
        if conflict:
            unread = self._next_unread(state, conflict)
            if unread:
                return self._read(unread, "读取时发现冲突，补充读取另一篇原文")
            return self._resolve_or_ask(state, conflict)

        return self._answer_from_section(last.data, "已读取相关片段，引用原文回答")

    def _filter_specific(self, hits: list[dict], query: str) -> list[dict]:
        """问题里的版本/规格 token（如 4K、1080P）必须在命中原文中出现。"""
        specific = {
            token
            for token in SPECIFIC_TOKEN_RE.findall(query.lower())
            if not DOC_ID_RE.match(token)
        }
        if not specific:
            return hits
        filtered = []
        for hit in hits:
            text = " ".join(
                str(hit.get(key, ""))
                for key in ("title", "heading", "content")
            )
            if specific <= tokenize(text):
                filtered.append(hit)
        return filtered

    def _filter_exceptions(self, hits: list[dict], query: str) -> list[dict]:
        """知识库未覆盖的例外场景（丢失、过期、补开等）不硬答。"""
        triggered = [term for term in GAP_SCENARIO_TERMS if term in query]
        if not triggered:
            return hits
        filtered = []
        for hit in hits:
            text = " ".join(
                str(hit.get(key, ""))
                for key in ("title", "heading", "content")
            )
            if all(term in text for term in triggered):
                filtered.append(hit)
        return filtered

    def _retry_or_fail(self, state: AgentState, last) -> Action:
        retries = state.retry_count.get(last.tool, 0)
        if retries < 1:
            state.retry_count[last.tool] = retries + 1
            return Action(
                type="tool",
                tool=last.tool,
                args=last.args,
                reason=f"{last.tool} 返回失败，按计划重试一次",
            )
        return Action(
            type="report_incomplete",
            status=STATUS_TOOL_ERROR,
            reason=f"{last.tool} 连续失败：{last.error or last.summary}",
        )

    def _next_unread(self, state: AgentState, conflict: dict) -> dict | None:
        for item in conflict["items"]:
            identity = f"{item['doc_id']}:{item['section_id']}"
            if identity not in state.read_sections:
                return item
        return None

    def _resolve_or_ask(self, state: AgentState, conflict: dict) -> Action:
        resolved = resolve_conflict(conflict, state.merged_question, self.synonyms)
        if resolved:
            return self._answer_from_item(
                resolved,
                f"冲突经适用范围/优先级规则裁决，采用 {resolved['doc_id']}",
            )

        parts = []
        for item in conflict["items"]:
            part = f"{item['doc_id']}={item['display']}"
            if item.get("scope"):
                part += f"（适用范围：{item['scope']}）"
            parts.append(part)
        question = (
            f"检测到“{conflict['field']}”存在资料冲突：{'、'.join(parts)}。"
            "这些说明缺少与当前问题匹配的适用范围或优先级，请确认适用哪一份制度。"
        )
        return Action(
            type="ask_user",
            question=question,
            conflicts=[conflict],
            gaps=["缺少与当前问题匹配的适用范围或优先级声明"],
            reason="冲突无法自动裁决，请求用户确认",
        )

    def _answer_from_hit(self, hit: dict, reason: str) -> Action:
        return self._answer(
            hit["doc_id"], hit["title"], hit["section_id"], hit["content"], reason
        )

    def _answer_from_section(self, section: dict, reason: str) -> Action:
        return self._answer(
            section["doc_id"],
            section["title"],
            section["section_id"],
            section["content"],
            reason,
        )

    def _answer_from_item(self, item: dict, reason: str) -> Action:
        return self._answer(
            item["doc_id"], item["title"], item["section_id"], item["quote"], reason
        )

    def _answer(
        self,
        doc_id: str,
        title: str,
        section_id: str,
        quote: str,
        reason: str,
    ) -> Action:
        return Action(
            type="answer",
            answer=f"根据 {doc_id}《{title}》{section_id}：{quote}",
            citations=[{
                "doc_id": doc_id,
                "section_id": section_id,
                "quote": quote,
            }],
            reason=reason,
        )
