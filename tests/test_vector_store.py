from __future__ import annotations

from pathlib import Path

from fake_embedder import ConceptEmbedder
from src.kb import KnowledgeBase

ROOT = Path(__file__).resolve().parents[1]


def test_vector_retrieval_for_unseen_paraphrase(tmp_path):
    kb = KnowledgeBase.load(
        ROOT / "data",
        embedder=ConceptEmbedder(),
        cache_path=tmp_path / "cache.json",
    )
    hits = kb.search("钱最晚什么时候能报", top_k=8)
    doc_ids = {hit["doc_id"] for hit in hits}
    assert {"D01", "D02"} <= doc_ids
    assert kb.retrieval_mode == "hybrid"
    assert any(hit["vector_score"] > 0 for hit in hits if hit["doc_id"] in {"D01", "D02"})


def test_faiss_backend_when_available(tmp_path):
    kb = KnowledgeBase.load(
        ROOT / "data",
        embedder=ConceptEmbedder(),
        cache_path=tmp_path / "cache.json",
    )
    try:
        import faiss  # noqa: F401
    except ImportError:
        expected = "numpy"
    else:
        expected = "faiss"
    assert kb.vector_index.backend == expected


def test_vector_only_paraphrase_ranks_relevant_docs_first(tmp_path):
    kb = KnowledgeBase.load(
        ROOT / "data",
        embedder=ConceptEmbedder(),
        cache_path=tmp_path / "cache.json",
    )
    hits = kb.search("钱最晚什么时候能报", top_k=8)
    assert hits[0]["doc_id"] in {"D01", "D02"}
    assert hits[0]["retrieval_mode"] == "hybrid"


def test_hybrid_keeps_materials_question_on_materials(tmp_path):
    kb = KnowledgeBase.load(
        ROOT / "data",
        embedder=ConceptEmbedder(),
        cache_path=tmp_path / "cache.json",
    )
    hits = kb.search("差旅报销需要哪些材料", top_k=8)
    top_sections = [hit["section_id"] for hit in hits[:3]]
    assert "D03-1" in top_sections


def test_embedding_cache_is_reused(tmp_path):
    class CountingEmbedder(ConceptEmbedder):
        def __init__(self):
            self.calls = 0

        def embed(self, texts, input_type=None):
            self.calls += 1
            return super().embed(texts, input_type)

    cache_path = tmp_path / "cache.json"
    first = CountingEmbedder()
    KnowledgeBase.load(ROOT / "data", embedder=first, cache_path=cache_path)
    assert first.calls == 1

    second = CountingEmbedder()
    KnowledgeBase.load(ROOT / "data", embedder=second, cache_path=cache_path)
    assert second.calls == 0


def test_keyword_fallback_when_embedder_fails(tmp_path):
    class BrokenEmbedder:
        provider = "broken"
        model = "broken"

        def embed(self, texts, input_type=None):
            raise RuntimeError("embedding service unavailable")

    kb = KnowledgeBase.load(
        ROOT / "data",
        embedder=BrokenEmbedder(),
        cache_path=tmp_path / "cache.json",
    )
    assert kb.vector_error
    hits = kb.search("云剪辑支持导出哪些格式", top_k=8)
    assert hits
    assert hits[0]["doc_id"] == "D04"
    assert kb.retrieval_mode == "keyword"
