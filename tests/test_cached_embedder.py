from __future__ import annotations

from pathlib import Path

from src.embeddings import CachedEmbedder, build_embedder_from_env
from src.kb import KnowledgeBase

ROOT = Path(__file__).resolve().parents[1]


def test_document_texts_use_cached_vectors():
    embedder = CachedEmbedder()
    entry = embedder.entries[0]
    vector = embedder.embed([entry["text"]], input_type="document")[0]
    assert vector == entry["vector"]


def test_paraphrase_maps_to_relevant_exemplar():
    embedder = CachedEmbedder()
    vector = embedder.embed(["去年没休完的年假怎么办"], input_type="query")[0]
    assert any(vector)
    assert embedder.last_mapping["score"] >= embedder.min_mapping_score
    assert "年假" in embedder.last_mapping["matched"]


def test_out_of_scope_query_does_not_map():
    embedder = CachedEmbedder()
    vector = embedder.embed(["食堂几点开门"], input_type="query")[0]
    assert not any(vector)


def test_default_embedder_without_env_uses_offline_cache(monkeypatch):
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    embedder = build_embedder_from_env()
    assert isinstance(embedder, CachedEmbedder)


def test_offline_hybrid_retrieval(tmp_path):
    kb = KnowledgeBase.load(
        ROOT / "data",
        embedder=CachedEmbedder(),
        cache_path=tmp_path / "cache.json",
    )
    assert kb.vector_index is not None
    assert kb.vector_index.backend in {"faiss", "numpy"}
    hits = kb.search("去年没休完的年假怎么办", top_k=5)
    assert hits[0]["section_id"] == "D05-2"
    assert kb.retrieval_mode == "hybrid"
