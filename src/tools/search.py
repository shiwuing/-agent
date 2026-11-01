from __future__ import annotations

from ..conflict import detect_conflicts
from ..models import ToolResult


def search_docs(kb, query: str, top_k: int = 8) -> ToolResult:
    hits = kb.search(query, top_k=top_k)
    conflict = detect_conflicts(hits, query=query)
    data = {
        "query": query,
        "hits": hits,
        "conflict_hint": conflict,
        "retrieval_mode": getattr(kb, "retrieval_mode", "keyword"),
    }

    if not hits:
        summary = "未命中任何文档片段"
    else:
        summary = f"命中 {len(hits)} 个片段"
        if conflict:
            summary += f"；检测到字段“{conflict['field']}”存在不一致"

    return ToolResult(ok=True, data=data, summary=summary)
