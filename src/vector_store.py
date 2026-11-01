from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np

try:  # faiss 是可选依赖；缺失时退回 numpy 暴力检索
    import faiss
except ImportError:  # pragma: no cover - 取决于安装环境
    faiss = None


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def cosine_similarity(a: list[float], b: list[float]) -> float:
    vector_a = np.asarray(a, dtype="float32")
    vector_b = np.asarray(b, dtype="float32")
    norm = float(np.linalg.norm(vector_a) * np.linalg.norm(vector_b))
    if norm == 0.0:
        return 0.0
    return float(np.dot(vector_a, vector_b) / norm)


class VectorIndex:
    """把文档分节与常见问法编码为向量，按余弦相似度召回。

    优先使用 FAISS 的 Inner Product 索引（向量已做 L2 归一化，等价于余弦），
    未安装 faiss 时退回 numpy 矩阵乘法。
    """

    def __init__(self, kb, embedder, cache_path: str | Path | None = None):
        self.kb = kb
        self.embedder = embedder
        self.cache_path = Path(cache_path) if cache_path else None
        # 低于阈值的向量命中视为噪声；0 表示不过滤（不同模型分布不同）。
        self.min_score = float(os.getenv("EMBEDDING_MIN_SCORE", "0.0"))
        self.corpus = self._build_corpus()
        self.entries: list[dict] = []
        self.backend = "none"
        self._index = None
        self._vectors: np.ndarray | None = None
        self._load_or_build()
        self._build_index()

    def _build_corpus(self) -> list[dict]:
        corpus: list[dict] = []
        for doc in self.kb.docs.values():
            for section in doc["sections"]:
                base = f"{doc['title']} {section['heading']} {section['content']}"
                corpus.append({
                    "doc_id": doc["doc_id"],
                    "section_id": section["section_id"],
                    "text": base,
                    "kind": "content",
                })
                for question in section.get("questions", []):
                    corpus.append({
                        "doc_id": doc["doc_id"],
                        "section_id": section["section_id"],
                        "text": question,
                        "kind": "question",
                    })
        return corpus

    def _fingerprint(self) -> str:
        payload = json.dumps(
            {
                "provider": self.embedder.provider,
                "model": self.embedder.model,
                "texts": [entry["text"] for entry in self.corpus],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _load_or_build(self) -> None:
        fingerprint = self._fingerprint()

        if self.cache_path and self.cache_path.exists():
            try:
                cached = json.loads(self.cache_path.read_text(encoding="utf-8"))
                if (
                    cached.get("fingerprint") == fingerprint
                    and len(cached.get("entries", [])) == len(self.corpus)
                ):
                    self.entries = cached["entries"]
                    return
            except (OSError, json.JSONDecodeError):
                pass

        vectors = self.embedder.embed(
            [entry["text"] for entry in self.corpus], input_type="document"
        )
        if len(vectors) != len(self.corpus):
            raise RuntimeError(
                f"embedding count mismatch: expected {len(self.corpus)}, got {len(vectors)}"
            )

        self.entries = [
            {**entry, "vector": vector}
            for entry, vector in zip(self.corpus, vectors)
        ]

        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(
                    {
                        "fingerprint": fingerprint,
                        "provider": self.embedder.provider,
                        "model": self.embedder.model,
                        "entries": self.entries,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    def _build_index(self) -> None:
        if not self.entries:
            self.backend = "none"
            return

        matrix = np.asarray(
            [entry["vector"] for entry in self.entries], dtype="float32"
        )
        if matrix.ndim != 2 or matrix.shape[1] == 0:
            raise RuntimeError("invalid embedding matrix")
        matrix = np.ascontiguousarray(_normalize_rows(matrix))
        self._vectors = matrix

        if faiss is not None:
            index = faiss.IndexFlatIP(matrix.shape[1])
            index.add(matrix)
            self._index = index
            self.backend = "faiss"
        else:
            self._index = None
            self.backend = "numpy"

    def search(self, query: str, top_k: int = 8) -> list[dict]:
        if not self.entries or self._vectors is None:
            return []

        raw = self.embedder.embed([query], input_type="query")[0]
        query_vector = np.asarray([raw], dtype="float32")
        if query_vector.shape[1] != self._vectors.shape[1]:
            raise RuntimeError(
                "query embedding dimension "
                f"{query_vector.shape[1]} != index dimension {self._vectors.shape[1]}"
            )
        query_vector = np.ascontiguousarray(_normalize_rows(query_vector))

        limit = min(len(self.entries), max(top_k * 4, top_k))
        if self._index is not None:
            scores, indices = self._index.search(query_vector, limit)
            candidates = [
                (float(score), int(index))
                for score, index in zip(scores[0], indices[0])
                if index >= 0
            ]
        else:
            similarities = self._vectors @ query_vector[0]
            order = np.argsort(-similarities)[:limit]
            candidates = [(float(similarities[i]), int(i)) for i in order]

        best: dict[tuple[str, str], dict] = {}
        for score, index in candidates:
            if score <= 0 or score < self.min_score:
                continue
            entry = self.entries[index]
            key = (entry["doc_id"], entry["section_id"])
            current = best.get(key)
            if current is None or score > current["vector_score"]:
                best[key] = {
                    "doc_id": entry["doc_id"],
                    "section_id": entry["section_id"],
                    "vector_score": score,
                    "matched_text": entry["text"],
                    "matched_kind": entry["kind"],
                }

        ranked = sorted(
            best.values(),
            key=lambda item: (-item["vector_score"], item["doc_id"], item["section_id"]),
        )
        results: list[dict] = []
        for item in ranked[:top_k]:
            section = self.kb.get_section(item["doc_id"], item["section_id"])
            if section is None:
                continue
            results.append({
                **section,
                "snippet": section["content"],
                "vector_score": round(item["vector_score"], 4),
                "matched_text": item["matched_text"],
                "matched_kind": item["matched_kind"],
            })
        return results
