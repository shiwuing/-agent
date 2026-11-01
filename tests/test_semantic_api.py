from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.embeddings import build_embedder_from_env
from src.kb import KnowledgeBase

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    not os.getenv("EMBEDDING_API_KEY")
    or os.getenv("EMBEDDING_PROVIDER", "none").lower() in {"", "none", "keyword", "off"},
    reason="embedding API not configured",
)


def test_real_embedding_handles_unseen_paraphrase(tmp_path):
    embedder = build_embedder_from_env()
    assert embedder is not None

    kb = KnowledgeBase.load(
        ROOT / "data",
        embedder=embedder,
        cache_path=tmp_path / "cache.json",
    )
    hits = kb.search("钱最晚什么时候能报", top_k=8)
    doc_ids = {hit["doc_id"] for hit in hits}
    assert {"D01", "D02"} <= doc_ids
