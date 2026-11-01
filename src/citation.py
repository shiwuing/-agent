from __future__ import annotations

import re

from .kb import KnowledgeBase, normalize


ID_RE = re.compile(r"\b[A-Za-z]\d+(?:-\d+)*\b")
# ISO 风格日期（2025-02-01 / 2025/02/01 / 2025年2月1日）属于文档元数据，
# 拆开后会变成 2025 / 02 / 01 三个伪数值断言，匹配数值前先整体剔除。
DATE_RE = re.compile(r"\d{4}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}\s*日?")
# 编号列表/序号（"1." "2）" "（3）" "第 3 点"）是排版标记，不是数值断言。
LIST_MARKER_RE = re.compile(r"(?m)^\s*\d{1,3}\s*[.、)）]\s*")
BRACKET_INDEX_RE = re.compile(r"[（(]\s*\d{1,3}\s*[)）]")
ORDINAL_RE = re.compile(
    r"第\s*(?:\d{1,3}|[零一二两三四五六七八九十百]+)\s*[点条项步次]"
)
NUM_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)(?![\d.])")
# 只有带单位/量词的数量才是需要核对的断言；"共 3 项""2 个文档"这类计数不算。
CLAIM_NUM_RE = re.compile(
    r"(?<![\d.])(\d{1,3}(?:\.\d+)?)"
    r"(?=\s*(?:个工作日|工作日|天|日|年|月|小时|分钟|元|%|％|岁|次|K|P))"
)
HYPOTHETICAL_RE = re.compile(
    r"例如|比如|假设|假如|举例|如需|若|如果"
    r"|如(?=\s*[0-9零一二两三四五六七八九十])"
)
SENTENCE_RE = re.compile(r"[^。！？；\n]+[。！？；\n]?")

CN_DIGITS = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3,
    "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
CN_MEASURE = (
    r"(?:次(?!性)|天|个|年|月|日|人|份|项|条|类|周|小时|分钟|工作日|岁|元)"
)
CN_NUMBER_RE = re.compile(
    rf"(?<![另这那某同每第])([零一二两三四五六七八九十百千万]+)"
    rf"(?=\s*{CN_MEASURE})"
)


def _cn_to_int(text: str) -> int:
    total = 0
    section = 0
    number = 0
    for char in text:
        if char in CN_DIGITS:
            number = CN_DIGITS[char]
        elif char in CN_UNITS:
            unit = CN_UNITS[char]
            if unit == 10000:
                section = (section + number) * unit
                total += section
                section = 0
                number = 0
            else:
                if number == 0:
                    number = 1
                section += number * unit
                number = 0
    return total + section + number


def _normalize_cn_numbers(text: str) -> str:
    """把「一次」「三十天」等中文数量词转成阿拉伯数字，便于和引用原文比对。"""
    return CN_NUMBER_RE.sub(
        lambda match: str(_cn_to_int(match.group(1))), text
    )


def _strip_ids(text: str) -> str:
    return ID_RE.sub(" ", text)


def _strip_non_claims(text: str) -> str:
    """去掉文档 ID、日期与编号标记，只保留真正需要核对引用的数值断言。"""
    text = DATE_RE.sub(" ", _strip_ids(text))
    text = ORDINAL_RE.sub(" ", text)
    text = BRACKET_INDEX_RE.sub(" ", text)
    return LIST_MARKER_RE.sub(" ", text)


def validate_citations(
    answer: str,
    citations: list[dict],
    kb: KnowledgeBase,
    observed_sections: list[dict] | None = None,
) -> tuple[bool, list[str]]:
    """校验引用存在、引用逐字匹配，且回答中的数值均来自引用原文。

    `observed_sections` 是本轮工具实际返回过的分节。只要数值出现在本轮
    工具结果中，就视为有依据，避免把「对比说明」误判为编造；模型凭记忆写出、
    本轮从未出现过的数值仍会被拦截。
    """
    errors: list[str] = []
    quote_texts: list[str] = []

    if not citations:
        errors.append("回答未提供任何引用")

    for index, citation in enumerate(citations, start=1):
        doc_id = citation.get("doc_id", "")
        section_id = citation.get("section_id", "")
        quote = citation.get("quote", "")
        if not doc_id or not section_id or not quote:
            errors.append(f"引用 {index} 字段不完整")
            continue

        section = kb.get_section(doc_id, section_id)
        if section is None:
            errors.append(f"引用 {index} 指向不存在的文档/分节：{doc_id}/{section_id}")
            continue

        content_norm = normalize(section["content"])
        quote_norm = normalize(quote)
        if quote_norm not in content_norm:
            errors.append(f"引用 {index} 的片段未逐字出现在 {doc_id}/{section_id} 中")
            continue
        quote_texts.append(content_norm)

    combined = _normalize_cn_numbers("".join(quote_texts))

    observed_numbers: set[str] = set()
    for section in observed_sections or []:
        observed_numbers.update(
            NUM_RE.findall(
                _normalize_cn_numbers(normalize(section.get("content", "")))
            )
        )

    stripped = _normalize_cn_numbers(_strip_non_claims(answer))
    for sentence_match in SENTENCE_RE.finditer(stripped):
        sentence = sentence_match.group(0)
        if HYPOTHETICAL_RE.search(sentence):
            # 「例如满 10 年」是说明缺口的假设，不是事实断言。
            continue
        for match in CLAIM_NUM_RE.finditer(sentence):
            number = match.group(1)
            if number in combined or number in observed_numbers:
                continue
            context = sentence.strip().replace("\n", " ")[:80]
            errors.append(
                f"回答中的数值 {number} 未出现在引用原文中（上下文：…{context}…）"
            )

    return len(errors) == 0, errors
