from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path
from typing import Protocol


CJK_RUN = re.compile(r"[一-鿿]+")
WORD = re.compile(r"[a-z0-9]+")
DEFAULT_OFFLINE_CACHE = (
    Path(__file__).resolve().parents[1] / "data" / "offline_embeddings.json"
)


def _tokenize(text: str) -> set[str]:
    """与 kb.tokenize 同口径的轻量分词，避免循环导入。"""
    lowered = text.lower()
    tokens: set[str] = set(WORD.findall(lowered))
    for run in CJK_RUN.findall(lowered):
        if len(run) == 1:
            tokens.add(run)
        for index in range(len(run) - 1):
            tokens.add(run[index:index + 2])
    return tokens


class Embedder(Protocol):
    provider: str
    model: str

    def embed(self, texts: list[str], input_type: str | None = None) -> list[list[float]]:
        ...


class OpenAICompatEmbedder:
    """OpenAI 兼容的 /embeddings 接口，也适用于多家兼容服务。"""

    provider = "openai"
    input_type_supported = False

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "text-embedding-3-small",
        timeout: float = 60.0,
        batch_size: int = 64,
    ):
        if not api_key:
            raise ValueError("embedding api key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.batch_size = batch_size

    def embed(self, texts: list[str], input_type: str | None = None) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            payload: dict = {"model": self.model, "input": batch}
            if input_type and self.input_type_supported:
                payload["input_type"] = input_type
            data = self._post(payload)
            items = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
            if len(items) != len(batch):
                raise RuntimeError(
                    f"embedding count mismatch: sent {len(batch)}, got {len(items)}"
                )
            vectors.extend(item["embedding"] for item in items)
        return vectors

    def _post(self, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/embeddings"
        last_error: Exception | None = None
        for attempt in range(3):
            request = urllib.request.Request(
                url, data=body, headers=headers, method="POST"
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                last_error = RuntimeError(
                    f"embedding HTTP {exc.code}: {detail}"
                )
                if exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(1.5 ** attempt)
                    continue
                raise last_error from exc
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < 2:
                    time.sleep(1.5 ** attempt)
                    continue
                raise
        raise RuntimeError(f"embedding request failed: {last_error}")


class VoyageEmbedder(OpenAICompatEmbedder):
    provider = "voyage"
    input_type_supported = True

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.voyageai.com/v1",
        model: str = "voyage-3",
        **kwargs,
    ):
        super().__init__(api_key, base_url=base_url, model=model, **kwargs)


class ArkMultimodalEmbedder:
    """火山方舟多模态 embedding 接口。

    该接口一次请求只编码一段输入，返回 `{"data": {"embedding": [...]}}`，
    与 OpenAI 的批量格式不同，因此单独实现。
    """

    provider = "ark"
    input_type_supported = False

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        model: str = "doubao-embedding-vision-251215",
        timeout: float = 60.0,
    ):
        if not api_key:
            raise ValueError("embedding api key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    @property
    def endpoint(self) -> str:
        if self.base_url.endswith("/embeddings/multimodal"):
            return self.base_url
        return f"{self.base_url}/embeddings/multimodal"

    def embed(self, texts: list[str], input_type: str | None = None) -> list[list[float]]:
        return [self._embed_text(text) for text in texts]

    def _embed_text(self, text: str) -> list[float]:
        payload = {
            "model": self.model,
            "input": [{"type": "text", "text": text}],
        }
        data = self._post(payload)
        item = data.get("data") if isinstance(data, dict) else None
        vector = item.get("embedding") if isinstance(item, dict) else None
        if not isinstance(vector, list) or not vector:
            raise RuntimeError(
                f"unexpected ark embedding response: {str(data)[:300]}"
            )
        return vector

    def _post(self, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(3):
            request = urllib.request.Request(
                self.endpoint, data=body, headers=headers, method="POST"
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                last_error = RuntimeError(
                    f"ark embedding HTTP {exc.code}: {detail}"
                )
                if exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(1.5 ** attempt)
                    continue
                raise last_error from exc
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < 2:
                    time.sleep(1.5 ** attempt)
                    continue
                raise
        raise RuntimeError(f"ark embedding request failed: {last_error}")


class CachedEmbedder:
    """离线向量：读取预计算的文档/问题向量，查询映射到最接近的问题样例。

    不需要任何 Embedding API、模型下载或 GPU。文档向量与问题样例向量由
    火山方舟预先算好；运行时只用 BM25 式的词法相似度选择样例。
    """

    input_type_supported = False

    def __init__(self, cache_path: str | Path = DEFAULT_OFFLINE_CACHE):
        path = Path(cache_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = payload.get("entries") or []
        if not entries:
            raise ValueError("offline embedding cache is empty")

        self.cache_path = path
        # provider/model 必须与缓存 fingerprint 一致，VectorIndex 才能直接复用缓存。
        self.provider = payload.get("provider", "cached")
        self.display_provider = "cached"
        self.model = payload.get("model", "unknown")
        self.entries = entries
        self._text_to_vector = {
            entry["text"]: entry["vector"] for entry in entries
        }
        self._dim = len(entries[0]["vector"])
        self.synonyms: dict[str, list[str]] = {}
        self.min_mapping_score = float(
            os.getenv("EMBEDDING_MAPPING_MIN_SCORE", "0.4")
        )
        self.last_mapping: dict | None = None

        exemplars = [entry for entry in entries if entry.get("kind") == "question"]
        if not exemplars:
            exemplars = entries
        self._exemplars = [
            {
                "text": entry["text"],
                "vector": entry["vector"],
                "tokens": _tokenize(entry["text"]),
            }
            for entry in exemplars
        ]

    def set_synonyms(self, synonyms: dict[str, list[str]]) -> None:
        self.synonyms = synonyms or {}

    def _expand(self, tokens: set[str], text: str) -> set[str]:
        expanded = set(tokens)
        lowered = text.lower()
        for canonical, group in self.synonyms.items():
            if any(term.lower() in lowered for term in group):
                expanded.add(canonical.lower())
                for term in group:
                    expanded.update(_tokenize(term))
        return expanded

    def _map_query(self, text: str) -> list[float]:
        from .kb import DOMAIN_KEYWORDS

        lowered = text.lower()
        if not any(keyword in lowered for keyword in DOMAIN_KEYWORDS):
            self.last_mapping = {
                "query": text,
                "matched": None,
                "score": 0.0,
                "reason": "no domain keyword",
            }
            return [0.0] * self._dim

        query_tokens = self._expand(_tokenize(text), text)
        if not query_tokens:
            self.last_mapping = {"query": text, "matched": None, "score": 0.0}
            return [0.0] * self._dim

        normalized_query = re.sub(r"\s+", "", text.lower())
        best_entry = None
        best_score = 0.0

        for exemplar in self._exemplars:
            overlap = query_tokens & exemplar["tokens"]
            coverage = len(overlap) / len(query_tokens)
            normalized_exemplar = re.sub(
                r"\s+", "", exemplar["text"].lower()
            )
            char_score = SequenceMatcher(
                None, normalized_query, normalized_exemplar
            ).ratio()
            score = 0.8 * char_score + 0.2 * coverage
            if normalized_query and (
                normalized_query in normalized_exemplar
                or normalized_exemplar in normalized_query
            ):
                score += 0.1
            if score > best_score:
                best_score = score
                best_entry = exemplar

        if best_entry is None or best_score < self.min_mapping_score:
            self.last_mapping = {
                "query": text,
                "matched": best_entry["text"] if best_entry else None,
                "score": round(best_score, 4),
            }
            return [0.0] * self._dim

        self.last_mapping = {
            "query": text,
            "matched": best_entry["text"],
            "score": round(best_score, 4),
        }
        return best_entry["vector"]

    def embed(
        self, texts: list[str], input_type: str | None = None
    ) -> list[list[float]]:
        if input_type == "document":
            vectors: list[list[float]] = []
            for text in texts:
                vector = self._text_to_vector.get(text)
                if vector is None:
                    raise RuntimeError(
                        "offline embedding cache is stale: document text "
                        "not found; rebuild it with "
                        "scripts/build_offline_embeddings.py"
                    )
                vectors.append(vector)
            return vectors
        return [self._map_query(text) for text in texts]


def _load_cached_embedder() -> CachedEmbedder | None:
    path = os.getenv("EMBEDDING_CACHE_PATH", "").strip() or DEFAULT_OFFLINE_CACHE
    try:
        return CachedEmbedder(path)
    except Exception:  # noqa: BLE001 - 缓存缺失/损坏时回退关键词
        return None


def build_embedder_from_env() -> Embedder | None:
    """按环境变量构建 Embedding 客户端；无 Key 时优先使用离线预计算向量。"""
    provider = os.getenv("EMBEDDING_PROVIDER", "").strip().lower()

    if provider in {"cached", "offline"}:
        return _load_cached_embedder()
    if provider in {"none", "keyword", "off"}:
        return None
    if provider in {"", "auto"}:
        # 没配置任何检索服务时，默认使用仓库内的离线向量缓存。
        return _load_cached_embedder()

    api_key = os.getenv("EMBEDDING_API_KEY", "").strip()
    if not api_key:
        api_key = (
            os.getenv("VOYAGE_API_KEY", "").strip()
            if provider == "voyage"
            else os.getenv("OPENAI_API_KEY", "").strip()
        )
    if not api_key:
        cached = _load_cached_embedder()
        if cached is not None:
            print(
                "[warn] 未配置 Embedding Key，使用离线预计算向量",
                file=sys.stderr,
            )
        return cached

    timeout = float(os.getenv("EMBEDDING_TIMEOUT", "60"))
    batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))

    if provider == "voyage":
        return VoyageEmbedder(
            api_key,
            base_url=os.getenv("EMBEDDING_BASE_URL", "https://api.voyageai.com/v1"),
            model=os.getenv("EMBEDDING_MODEL", "voyage-3"),
            timeout=timeout,
            batch_size=batch_size,
        )

    if provider in {"ark", "volcengine", "doubao"}:
        return ArkMultimodalEmbedder(
            api_key,
            base_url=os.getenv(
                "EMBEDDING_BASE_URL",
                "https://ark.cn-beijing.volces.com/api/v3",
            ),
            model=os.getenv(
                "EMBEDDING_MODEL", "doubao-embedding-vision-251215"
            ),
            timeout=timeout,
        )

    return OpenAICompatEmbedder(
        api_key,
        base_url=os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1"),
        model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        timeout=timeout,
        batch_size=batch_size,
    )
