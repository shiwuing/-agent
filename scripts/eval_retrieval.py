from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.kb import KnowledgeBase  # noqa: E402
from src.main import load_env_file  # noqa: E402


def build_kb(data_dir: Path, use_vector: bool) -> KnowledgeBase:
    embedder = None
    if use_vector:
        from src.embeddings import build_embedder_from_env

        try:
            embedder = build_embedder_from_env()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] Embedding 初始化失败：{exc}", file=sys.stderr)
        if embedder is None:
            print(
                "[warn] 未配置 EMBEDDING_PROVIDER / EMBEDDING_API_KEY，回退关键词检索",
                file=sys.stderr,
            )

    kb = KnowledgeBase.load(data_dir, embedder=embedder)
    if kb.vector_error:
        print(f"[warn] 向量索引不可用：{kb.vector_error}", file=sys.stderr)
    return kb


def evaluate(kb: KnowledgeBase, cases: list[dict], top_k: int) -> dict:
    rows: list[dict] = []
    reciprocal_ranks: list[float] = []
    hit_count = 0
    counted = 0

    for case in cases:
        query = case["query"]
        expected = case.get("expected", [])
        hits = kb.search(query, top_k=top_k)
        section_ids = [hit["section_id"] for hit in hits]
        row = {
            "query": query,
            "expected": expected,
            "hits": section_ids,
            "mode": kb.retrieval_mode,
            "first_rank": None,
        }
        if expected:
            counted += 1
            rank = next(
                (
                    index + 1
                    for index, section_id in enumerate(section_ids)
                    if section_id in expected
                ),
                None,
            )
            row["first_rank"] = rank
            reciprocal_ranks.append(1.0 / rank if rank else 0.0)
            if rank:
                hit_count += 1
        rows.append(row)

    return {
        "rows": rows,
        "recall": hit_count / counted if counted else 0.0,
        "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks)
        if reciprocal_ranks
        else 0.0,
        "counted": counted,
        "top_k": top_k,
        "retrieval_mode": "hybrid" if kb.vector_index is not None else kb.retrieval_mode,
        "backend": getattr(kb.vector_index, "backend", "none")
        if kb.vector_index
        else "none",
    }


def print_result(title: str, result: dict) -> None:
    print(f"\n== {title} ==")
    print(
        f"mode={result['retrieval_mode']} backend={result['backend']}  "
        f"recall@{result['top_k']}={result['recall']:.3f}  mrr={result['mrr']:.3f}"
    )
    for row in result["rows"]:
        expected = ",".join(row["expected"]) or "(out-of-scope)"
        hits = ",".join(row["hits"][:5]) or "-"
        rank = row["first_rank"] if row["first_rank"] is not None else "-"
        print(f"  {row['query']:<16} expected={expected:<14} rank={rank:<3} hits={hits}")


def main(argv=None) -> int:
    load_env_file(ROOT / ".env")

    parser = argparse.ArgumentParser(description="检索评测：关键词 vs 关键词+向量混合")
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--eval", default=str(ROOT / "examples" / "retrieval_eval.json"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--keyword-only", action="store_true")
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.eval).read_text(encoding="utf-8"))
    cases = payload["cases"] if isinstance(payload, dict) else payload
    data_dir = Path(args.data_dir)

    keyword_result = evaluate(build_kb(data_dir, use_vector=False), cases, args.top_k)
    print_result("keyword", keyword_result)

    if args.keyword_only:
        return 0

    hybrid_kb = build_kb(data_dir, use_vector=True)
    if hybrid_kb.vector_index is None:
        print("\n[skip] 向量索引未启用，只输出关键词结果。")
        return 0

    hybrid_result = evaluate(hybrid_kb, cases, args.top_k)
    print_result(f"hybrid({hybrid_result['backend']})", hybrid_result)

    delta = hybrid_result["recall"] - keyword_result["recall"]
    print(
        f"\nRecall delta: {delta:+.3f}  "
        f"MRR delta: {hybrid_result['mrr'] - keyword_result['mrr']:+.3f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
