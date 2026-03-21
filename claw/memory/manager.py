from __future__ import annotations
import logging
import math
from datetime import datetime, timezone
from claw.memory.sqlite_store import MemoryStore
from claw.llm.router_client import LLMRouterClient

logger = logging.getLogger(__name__)

_FALLBACK_DIM = 768


class MemoryManager:
    def __init__(self, store: MemoryStore, llm: LLMRouterClient):
        self.store = store
        self.llm = llm

    async def save(
        self, session_id: str, content: str, metadata: dict | None = None
    ) -> str:
        """Save memory, auto-generate embedding. Returns memory_id."""
        embedding = await self._get_embedding(content)
        memory_id = await self.store.add(session_id, content, embedding, metadata)
        return memory_id

    async def search(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 5,
        hybrid_weight: float = 0.7,  # vector weight; BM25 = 1 - hybrid_weight
    ) -> list[dict]:
        """Hybrid search (RRF) + temporal decay."""
        query_emb = await self._get_embedding(query)

        # Vector search
        vec_results = await self.store.vector_search(query_emb, session_id, limit * 2)

        # BM25 search (gracefully ignore errors)
        try:
            bm25_results = await self.store.fts_search(query, session_id, limit * 2)
        except Exception as e:
            logger.warning(f"FTS search failed: {e}, falling back to vector only")
            bm25_results = []

        # Hybrid fusion + temporal decay
        fused = self._fuse_results(vec_results, bm25_results, hybrid_weight)
        fused = self._apply_temporal_decay(fused)

        return sorted(fused, key=lambda x: x["score"], reverse=True)[:limit]

    async def forget(self, memory_id: str) -> None:
        await self.store.delete(memory_id)

    async def _get_embedding(self, text: str) -> list[float]:
        """Generate embedding via LLM-Router /v1/embeddings. Falls back to zero vector."""
        try:
            embedding = await self.llm.get_embedding(text)
            return embedding
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return [0.0] * _FALLBACK_DIM

    def _fuse_results(
        self, vec: list[dict], bm25: list[dict], vec_weight: float
    ) -> list[dict]:
        """Reciprocal Rank Fusion (RRF)."""
        k = 60  # RRF constant
        scores: dict[str, float] = {}

        for rank, item in enumerate(vec):
            scores[item["id"]] = scores.get(item["id"], 0.0) + vec_weight / (k + rank + 1)

        for rank, item in enumerate(bm25):
            scores[item["id"]] = scores.get(item["id"], 0.0) + (1 - vec_weight) / (k + rank + 1)

        # Combine with content info
        id_to_item: dict[str, dict] = {}
        for item in vec + bm25:
            id_to_item.setdefault(item["id"], item)

        results = []
        for id_, score in scores.items():
            item = id_to_item[id_].copy()
            item["score"] = score
            results.append(item)

        return results

    def _apply_temporal_decay(self, results: list[dict]) -> list[dict]:
        """score *= exp(-decay_rate * days_old)."""
        now = datetime.now(timezone.utc)
        decay_rate = 0.05  # 5% decay per day
        for r in results:
            try:
                created = datetime.fromisoformat(r["created_at"])
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                days_old = (now - created).total_seconds() / 86400
                r["score"] *= math.exp(-decay_rate * days_old)
            except Exception:
                pass
        return results
