from __future__ import annotations

from ..models import ToolResult


def read_document(kb, doc_id: str, section_id: str | None = None) -> ToolResult:
    doc = kb.docs.get(doc_id)
    if doc is None:
        return ToolResult(ok=False, error=f"文档不存在: {doc_id}", summary="读取失败：文档不存在")

    if section_id is None:
        return ToolResult(
            ok=True,
            data={
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "version_date": doc["version_date"],
                "scope": doc.get("scope"),
                "priority": doc.get("priority"),
                "sections": doc["sections"],
            },
            summary=f"读取文档 {doc_id} 全文",
        )

    section = kb.get_section(doc_id, section_id)
    if section is None:
        return ToolResult(
            ok=False,
            error=f"分节不存在: {doc_id}/{section_id}",
            summary="读取失败：分节不存在",
        )
    return ToolResult(ok=True, data=section, summary=f"读取 {doc_id}/{section_id}")
