from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from .vector_store import VectorIndex


CJK_RUN = re.compile(r"[一-鿿]+")
WORD = re.compile(r"[a-z0-9]+")

# 只有问题里出现这些词，才认为它可能在知识库范围内。
# 这是防止 BM25 对「番茄炒蛋怎么做」这类问题也返回弱命中的门槛。
DOMAIN_KEYWORDS = {
    "报", "报销", "报账", "提交", "差旅", "出差", "年假", "带薪假",
    "休假", "假期", "云剪辑", "剪辑", "字幕", "审批", "批下来", "批复",
    "材料", "单据", "发票", "行程单", "导出", "输出", "格式", "视频",
    "期限", "时限", "费用", "入职", "跨年", "结转", "工龄", "垫付",
    "垫的钱", "拿回", "到账", "制度", "财务", "报销单",
}

QUERY_REWRITES = {
    "交上去": "提交",
    "批下来": "审批",
    "垫的钱": "报销",
    "垫付": "报销",
    "拿回来": "到账",
    "拿回": "到账",
    "没休完": "跨年",
    "没用完": "跨年",
    "输出": "导出",
    "单据": "材料",
    "假期": "年假",
}


def rewrite_terms(text: str) -> str:
    rewritten = text
    for source, target in QUERY_REWRITES.items():
        rewritten = rewritten.replace(source, target)
    return rewritten


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def tokenize_list(text: str) -> list[str]:
    """保留重复次数的分词，供 BM25 计算词频。"""
    text = text.lower()
    tokens: list[str] = list(WORD.findall(text))
    for run in CJK_RUN.findall(text):
        if len(run) == 1:
            tokens.append(run)
        tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def tokenize(text: str) -> set[str]:
    return set(tokenize_list(text))


class KnowledgeBase:
    def __init__(
        self,
        docs: list[dict],
        synonyms: dict[str, list[str]],
        embedder=None,
        cache_path: str | Path | None = None,
    ):
        self.docs = {doc["doc_id"]: doc for doc in docs}
        self.synonyms = synonyms
        self.embedder = embedder
        self.vector_index: VectorIndex | None = None
        self.vector_error: str | None = None
        self.retrieval_mode = "keyword"

        if embedder is not None:
            if hasattr(embedder, "set_synonyms"):
                embedder.set_synonyms(self.synonyms)
            try:
                self.vector_index = VectorIndex(
                    self, embedder, cache_path=cache_path
                )
            except Exception as exc:  # noqa: BLE001
                self.vector_error = str(exc)

    @classmethod
    def load(
        cls,
        data_dir: str | Path,
        embedder=None,
        cache_path: str | Path | None = None,
    ) -> "KnowledgeBase":
        data_dir = Path(data_dir)
        payload = json.loads((data_dir / "docs.json").read_text(encoding="utf-8"))
        docs = payload["docs"] if isinstance(payload, dict) else payload
        synonyms_path = data_dir / "synonyms.json"
        synonyms = (
            json.loads(synonyms_path.read_text(encoding="utf-8"))
            if synonyms_path.exists()
            else {}
        )
        if cache_path is None and embedder is not None:
            cache_path = getattr(embedder, "cache_path", None) or (
                data_dir / ".embedding_cache.json"
            )
        return cls(docs, synonyms, embedder=embedder, cache_path=cache_path)

    def expand_terms(self, query: str) -> set[str]:
        terms = tokenize(query)
        lowered = query.lower()
        for canonical, group in self.synonyms.items():
            if any(term.lower() in lowered for term in group):
                terms.add(canonical.lower())
                for term in group:
                    terms.update(tokenize(term))
        return terms

    K1 = 1.5
    B = 0.75
    MIN_KEYWORD_COVERAGE = 0.18

    def _keyword_search(self, query: str, top_k: int) -> list[dict]:
        search_query = rewrite_terms(query)
        lowered = search_query.lower()
        if not any(keyword in lowered for keyword in DOMAIN_KEYWORDS):
            return []

        terms = self.expand_terms(search_query)
        query_tokens = tokenize(search_query)
        if not terms or not query_tokens:
            return []

        prepared: list[tuple[dict, dict, str, Counter, int, set[str]]] = []
        for doc in self.docs.values():
            for section in doc["sections"]:
                questions = " ".join(section.get("questions", []))
                haystack = (
                    f"{doc['title']} {section['heading']} "
                    f"{section['content']} {questions}"
                )
                counts = Counter(tokenize_list(haystack))
                prepared.append(
                    (
                        doc,
                        section,
                        haystack,
                        counts,
                        sum(counts.values()),
                        set(counts),
                    )
                )

        if not prepared:
            return []
        total = len(prepared)
        avgdl = sum(item[4] for item in prepared) / total or 1.0

        document_frequency = Counter()
        for term in terms:
            document_frequency[term] = sum(
                1 for item in prepared if item[3].get(term, 0) > 0
            )
        idf = {
            term: math.log(
                1 + (total - document_frequency[term] + 0.5)
                / (document_frequency[term] + 0.5)
            )
            for term in terms
        }

        query_norm = normalize(search_query)
        hits: list[dict] = []
        for doc, section, haystack, counts, length, haystack_tokens in prepared:
            coverage = len(query_tokens & haystack_tokens) / len(query_tokens)
            if (
                coverage < self.MIN_KEYWORD_COVERAGE
                and query_norm not in normalize(haystack)
            ):
                continue
            score = 0.0
            for term in terms:
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + self.K1 * (
                    1 - self.B + self.B * length / avgdl
                )
                score += (
                    idf[term]
                    * frequency
                    * (self.K1 + 1)
                    / denominator
                )
            if query_norm and query_norm in normalize(haystack):
                score += 2.0
            if score <= 0:
                continue
            hits.append({
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "version_date": doc["version_date"],
                "scope": doc.get("scope"),
                "priority": doc.get("priority"),
                "section_id": section["section_id"],
                "heading": section["heading"],
                "content": section["content"],
                "snippet": section["content"],
                "score": round(score, 3),
            })

        hits.sort(key=lambda hit: (-hit["score"], hit["doc_id"], hit["section_id"]))
        return hits[:top_k]

    def search(self, query: str, top_k: int = 8) -> list[dict]:
        keyword_hits = self._keyword_search(query, max(top_k * 2, 8))

        vector_hits: list[dict] = []
        if self.vector_index is not None:
            try:
                vector_hits = self.vector_index.search(query, max(top_k * 2, 8))
                self.retrieval_mode = "hybrid"
            except Exception as exc:  # noqa: BLE001
                self.vector_error = str(exc)
                self.retrieval_mode = "keyword"

        if not vector_hits:
            self.retrieval_mode = "keyword"
            for hit in keyword_hits:
                hit["vector_score"] = 0.0
                hit["retrieval_mode"] = "keyword"
            return keyword_hits[:top_k]

        # Reciprocal Rank Fusion：两路分数口径不同，用名次融合更稳。
        rrf_k = 60
        merged: dict[tuple[str, str], dict] = {}

        def merge(hit: dict, source: str, rank: int) -> None:
            key = (hit["doc_id"], hit["section_id"])
            item = merged.get(key)
            if item is None:
                item = {
                    **hit,
                    "keyword_score": 0.0,
                    "vector_score": 0.0,
                    "rrf_score": 0.0,
                    "matched_text": None,
                    "matched_kind": source,
                }
                merged[key] = item
            if source == "keyword":
                item["keyword_score"] = float(hit.get("score", 0.0))
            else:
                item["vector_score"] = float(hit.get("vector_score", 0.0))
                if hit.get("matched_text"):
                    item["matched_text"] = hit["matched_text"]
                    item["matched_kind"] = hit.get("matched_kind", "vector")
            item["rrf_score"] += 1.0 / (rrf_k + rank)

        for rank, hit in enumerate(keyword_hits, start=1):
            merge(hit, "keyword", rank)
        for rank, hit in enumerate(vector_hits, start=1):
            merge(hit, "vector", rank)

        results: list[dict] = []
        for item in merged.values():
            item["score"] = round(item["rrf_score"], 6)
            item["retrieval_mode"] = "hybrid"
            item.pop("rrf_score", None)
            results.append(item)

        results.sort(
            key=lambda hit: (
                -hit["score"],
                -hit["vector_score"],
                hit["doc_id"],
                hit["section_id"],
            )
        )
        return results[:top_k]

    def get_section(self, doc_id: str, section_id: str) -> dict | None:
        doc = self.docs.get(doc_id)
        if doc is None:
            return None
        for section in doc["sections"]:
            if section["section_id"] == section_id:
                return {
                    "doc_id": doc["doc_id"],
                    "title": doc["title"],
                    "version_date": doc["version_date"],
                    "scope": doc.get("scope"),
                    "priority": doc.get("priority"),
                    "section_id": section["section_id"],
                    "heading": section["heading"],
                    "content": section["content"],
                }
        return None
