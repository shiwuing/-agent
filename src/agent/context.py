from __future__ import annotations


STOPWORDS = [
    "请问", "麻烦", "帮我", "一下", "是多久", "是多少", "什么", "哪些",
    "怎么", "如何", "为什么", "可以", "能否", "几点", "多久", "吗", "呢",
    "？", "?", "。", "，", ",",
]


FOLLOWUP_MARKERS = (
    "那", "它", "这个", "上述", "前面", "上面", "刚才", "那么",
)


def _topic_terms(text: str) -> list[str]:
    """从上一轮问题里提取主题词，避免整句历史压过当前追问。"""
    from ..kb import DOMAIN_KEYWORDS

    lowered = text.lower()
    selected: list[str] = []
    for word in sorted(DOMAIN_KEYWORDS, key=len, reverse=True):
        if word not in lowered:
            continue
        if any(word in existing for existing in selected):
            continue
        selected.append(word)
    selected.sort(key=lowered.index)
    return selected[:2]


def merge_history(question: str, history: list[dict] | None) -> str:
    """仅当问题含明确追问标记时，合并上一轮用户问题。

    不能用「问题很短」作为追问依据：短问题可能是全新话题
    （如「食堂几点开门」），合并会导致答非所问。
    """
    if not history:
        return question

    last_user = ""
    for turn in reversed(history):
        if turn.get("role") == "user" and turn.get("content"):
            last_user = turn["content"]
            break
    if not last_user:
        return question

    stripped = question.rstrip("？?。.!！ ")
    is_followup = (
        any(marker in question for marker in FOLLOWUP_MARKERS)
        or stripped.endswith("呢")
    )
    if is_followup:
        topic = " ".join(_topic_terms(last_user))
        if topic:
            return f"{topic} {question}"
        return f"{last_user} {question}"
    return question


def rewrite_query(query: str, synonyms: dict[str, list[str]], attempt: int) -> str:
    """无命中时改写查询：先去掉疑问/口语词，再追加同义词。"""
    out = query
    if attempt >= 1:
        for word in STOPWORDS:
            out = out.replace(word, " ")
    if attempt >= 2:
        for terms in synonyms.values():
            if any(term in query for term in terms):
                out += " " + " ".join(terms)

    cleaned = " ".join(out.split())
    return cleaned or query
