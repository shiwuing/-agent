from __future__ import annotations

import re


FIELD_RULES = [
    {
        "field": "报销期限",
        "keywords": ["报销期限", "报销时限"],
        "heading_keywords": ["时限", "期限"],
        "query_keywords": [
            "报销期限", "报销时限", "期限", "时限", "多久",
            "几天", "时间限制", "提交时限", "费用报销期限",
        ],
    },
    {
        "field": "年假天数",
        "keywords": ["年假", "带薪年假"],
        "heading_keywords": ["年假"],
        "query_keywords": ["年假", "带薪年假", "休假", "几天"],
    },
    {
        "field": "导出格式",
        "keywords": ["导出格式", "视频格式"],
        "heading_keywords": ["导出", "格式"],
        "query_keywords": ["导出格式", "导出", "格式", "视频格式", "mp4", "mov"],
    },
]

VALUE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(天|日|个工作日|%|元|小时|分钟)")


def _match_field(section: dict) -> str | None:
    heading = section.get("heading", "")
    content = section.get("content") or section.get("snippet") or ""
    for rule in FIELD_RULES:
        if any(keyword in heading or keyword in content for keyword in rule["keywords"]):
            return rule["field"]
        if any(keyword in heading for keyword in rule["heading_keywords"]):
            return rule["field"]
    return None


def _field_relevant(field: str, query: str) -> bool:
    lowered = query.lower()
    if field == "报销期限":
        strong_terms = [
            "报销期限", "报销时限", "费用报销期限", "提交时限",
            "时限", "期限", "报销时间",
        ]
        if any(term in lowered for term in strong_terms):
            return True
        reimburse_terms = [
            "报销", "费用", "差旅", "垫付", "垫的钱", "拿回", "到账",
        ]
        time_terms = [
            "多久", "几天", "多少天", "天内", "什么时候",
            "最晚", "时间限制", "时间",
        ]
        return (
            any(term in lowered for term in reimburse_terms)
            and any(term in lowered for term in time_terms)
        )

    for rule in FIELD_RULES:
        if rule["field"] == field:
            return any(keyword.lower() in lowered for keyword in rule["query_keywords"])
    return True


def _extract_value(content: str) -> tuple[str, str] | None:
    match = VALUE_RE.search(content)
    if match is None:
        return None
    raw_number, unit = match.group(1), match.group(2)
    number = str(int(float(raw_number))) if float(raw_number).is_integer() else raw_number
    return number, f"{raw_number} {unit}"


def detect_conflicts(sections: list[dict], query: str | None = None) -> dict | None:
    """同一字段出现不同数值时返回冲突描述。

    query 不为空时，只考虑与问题主题相关的字段，避免「问材料却触发期限冲突」。
    """
    grouped: dict[str, list[dict]] = {}
    seen: set[tuple[str, str]] = set()

    for section in sections:
        identity = (section.get("doc_id", ""), section.get("section_id", ""))
        if identity in seen:
            continue
        seen.add(identity)

        field = _match_field(section)
        if field is None:
            continue
        if query is not None and not _field_relevant(field, query):
            continue
        content = section.get("content") or section.get("snippet") or ""
        value = _extract_value(content)
        if value is None:
            continue

        number, display = value
        grouped.setdefault(field, []).append({
            "doc_id": section.get("doc_id", ""),
            "title": section.get("title", ""),
            "section_id": section.get("section_id", ""),
            "heading": section.get("heading", ""),
            "quote": content,
            "value": number,
            "display": display,
            "scope": section.get("scope"),
            "priority": section.get("priority"),
            "version_date": section.get("version_date"),
        })

    for field, items in grouped.items():
        values = {item["value"] for item in items}
        if len(values) > 1:
            return {"field": field, "items": items, "values": sorted(values)}
    return None


def resolve_conflict(
    conflict: dict,
    question: str,
    synonyms: dict[str, list[str]],
) -> dict | None:
    """按用户点名 -> 适用范围 -> 显式优先级 -> 文档声明的版本规则依次裁决。"""
    items = conflict["items"]

    explicit_docs = {
        match.upper()
        for match in re.findall(r"\bD\d+\b", question, re.IGNORECASE)
    }
    if explicit_docs:
        selected = [
            item for item in items
            if item.get("doc_id", "").upper() in explicit_docs
        ]
        if len({item["value"] for item in selected}) == 1:
            return selected[0]

    def scope_matches(item: dict) -> bool:
        scope = item.get("scope")
        if not scope:
            return False
        if scope in question:
            return True
        return any(term in question for term in synonyms.get(scope, []))

    scoped = [item for item in items if scope_matches(item)]
    if scoped:
        values = {item["value"] for item in scoped}
        if len(values) == 1:
            return scoped[0]

    prioritized = [item for item in items if item.get("priority") is not None]
    if prioritized:
        top_priority = max(item["priority"] for item in prioritized)
        top = [item for item in prioritized if item["priority"] == top_priority]
        if len({item["value"] for item in top}) == 1:
            return top[0]

    if any("以最新版本为准" in (item.get("quote") or "") for item in items):
        return max(items, key=lambda item: item.get("version_date") or "")

    return None
