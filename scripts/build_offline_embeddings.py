from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.embeddings import build_embedder_from_env  # noqa: E402
from src.kb import KnowledgeBase  # noqa: E402
from src.main import load_env_file  # noqa: E402


def main() -> int:
    load_env_file(ROOT / ".env")

    embedder = build_embedder_from_env()
    if embedder is None:
        print(
            "未配置 Embedding 服务。请在 .env 中设置 EMBEDDING_PROVIDER / "
            "EMBEDDING_API_KEY 后重试。",
            file=sys.stderr,
        )
        return 1
    if getattr(embedder, "display_provider", None) == "cached":
        print(
            "当前是无 Key 的离线缓存模式，无法重新生成向量。"
            "请配置真实 Embedding 服务后重试。",
            file=sys.stderr,
        )
        return 1

    data_dir = ROOT / "data"
    live_cache = data_dir / ".embedding_cache.json"
    offline_cache = data_dir / "offline_embeddings.json"

    kb = KnowledgeBase.load(data_dir, embedder=embedder)
    if kb.vector_error:
        print(f"向量索引构建失败：{kb.vector_error}", file=sys.stderr)
        return 1
    if not live_cache.exists():
        print(f"未生成缓存：{live_cache}", file=sys.stderr)
        return 1

    payload = json.loads(live_cache.read_text(encoding="utf-8"))
    offline_cache.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    dim = len(payload["entries"][0]["vector"]) if payload["entries"] else 0
    print(
        f"已写入 {offline_cache}：{len(payload['entries'])} 条向量，"
        f"维度 {dim}，模型 {payload.get('model')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
