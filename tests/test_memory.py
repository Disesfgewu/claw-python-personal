import pytest
from claw.memory.sqlite_store import MemoryStore


@pytest.mark.asyncio
async def test_memory_save_and_vector_search(tmp_path):
    store = MemoryStore(str(tmp_path / "claw.db"), embedding_dim=4)
    await store.init()

    emb = [0.1, 0.2, 0.3, 0.4]
    mid = await store.add("agent:main", "test content", emb, {"tags": ["test"]})
    assert mid

    results = await store.vector_search(emb, "agent:main", 5)
    assert len(results) == 1
    assert results[0]["content"] == "test content"
    assert results[0]["score"] >= 0.0


@pytest.mark.asyncio
async def test_fts_search(tmp_path):
    store = MemoryStore(str(tmp_path / "claw.db"), embedding_dim=4)
    await store.init()

    emb = [0.1, 0.2, 0.3, 0.4]
    await store.add("agent:main", "important meeting notes", emb, None)

    results = await store.fts_search("meeting", "agent:main", 5)
    assert len(results) == 1
    assert "meeting" in results[0]["content"]


@pytest.mark.asyncio
async def test_delete_memory(tmp_path):
    store = MemoryStore(str(tmp_path / "claw.db"), embedding_dim=4)
    await store.init()

    emb = [0.1, 0.2, 0.3, 0.4]
    mid = await store.add("agent:main", "to be deleted", emb, None)
    await store.delete(mid)

    results = await store.vector_search(emb, "agent:main", 5)
    assert len(results) == 0


from datetime import datetime, timezone

def test_rrf_fusion_combines_scores():
    """出現在 vector + BM25 兩個結果的 id，RRF score 應大於只出現一次的。"""
    from claw.memory.manager import MemoryManager
    manager = MemoryManager.__new__(MemoryManager)

    now_str = datetime.now(timezone.utc).isoformat()
    vec = [
        {"id": "a", "content": "hello world", "created_at": now_str, "score": 0.9},
        {"id": "b", "content": "foo bar", "created_at": now_str, "score": 0.5},
    ]
    bm25 = [
        {"id": "a", "content": "hello world", "created_at": now_str, "score": 0.8},
        {"id": "c", "content": "baz qux", "created_at": now_str, "score": 0.4},
    ]
    fused = manager._fuse_results(vec, bm25, 0.7)

    id_to_score = {item["id"]: item["score"] for item in fused}
    # "a" 同時出現在 vec + bm25，score 應最高
    assert id_to_score["a"] > id_to_score.get("b", 0)
    assert id_to_score["a"] > id_to_score.get("c", 0)


def test_temporal_decay_reduces_old_scores():
    """30 天前的記憶 score 應顯著低於新記憶。"""
    from claw.memory.manager import MemoryManager
    from datetime import datetime, timezone, timedelta
    manager = MemoryManager.__new__(MemoryManager)

    old_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    new_date = datetime.now(timezone.utc).isoformat()
    results = [
        {"id": "old", "content": "old memory", "created_at": old_date, "score": 1.0},
        {"id": "new", "content": "new memory", "created_at": new_date, "score": 1.0},
    ]
    decayed = manager._apply_temporal_decay(results)
    id_to_score = {r["id"]: r["score"] for r in decayed}
    assert id_to_score["new"] > id_to_score["old"]
    # 30 天衰減率 5%/天：exp(-0.05*30) ≈ 0.22
    assert id_to_score["old"] < 0.3
