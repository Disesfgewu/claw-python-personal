from __future__ import annotations
import uuid
import json
import struct
import aiosqlite
import sqlite_vec
from datetime import datetime, timedelta

from claw.core.storage import now_iso


class MemoryStore:
    def __init__(self, db_path: str, embedding_dim: int = 768):
        self.db_path = db_path
        self.embedding_dim = embedding_dim
        self.search_cache: dict[str, tuple[datetime, list[dict]]] = {}
        self.cache_ttl_seconds = 300

    def _get_cached_results(self, cache_key: str) -> list[dict] | None:
        if cache_key not in self.search_cache:
            return None
        cached_time, cached_results = self.search_cache[cache_key]
        if datetime.now() - cached_time < timedelta(seconds=self.cache_ttl_seconds):
            return cached_results
        self.search_cache.pop(cache_key, None)
        return None

    def _set_cached_results(self, cache_key: str, results: list[dict]) -> None:
        self.search_cache[cache_key] = (datetime.now(), results)

    def clear_cache(self) -> None:
        self.search_cache.clear()

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.enable_load_extension(True)
            await db.load_extension(sqlite_vec.loadable_path())

            # FTS5 for BM25 search
            await db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    memory_id UNINDEXED,
                    content,
                    tokenize = 'porter unicode61'
                )
            """)
            # Metadata table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS memory_vectors (
                    id TEXT PRIMARY KEY,
                    rowid_key INTEGER UNIQUE,
                    session_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_session
                ON memory_vectors(session_id)
            """)

            # Check if existing memory_vec table has a different dimension
            async with db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='memory_vec'"
            ) as cur:
                row = await cur.fetchone()

            if row and f"float[{self.embedding_dim}]" not in (row[0] or ""):
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Recreating memory_vec with dimension={self.embedding_dim}")
                await db.execute("DROP TABLE IF EXISTS memory_vec")

            # vec0 virtual table for ANN
            await db.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING vec0("
                f"embedding float[{self.embedding_dim}])"
            )
            await db.commit()

    async def add(
        self,
        session_id: str,
        content: str,
        embedding: list[float],
        metadata: dict | None,
    ) -> str:
        self.clear_cache()
        memory_id = str(uuid.uuid4())
        created_at = now_iso()
        meta_json = json.dumps(metadata) if metadata else None

        async with aiosqlite.connect(self.db_path) as db:
            await db.enable_load_extension(True)
            await db.load_extension(sqlite_vec.loadable_path())

            # Insert metadata — get auto rowid
            await db.execute(
                "INSERT INTO memory_vectors(id, session_id, content, created_at, metadata) VALUES (?,?,?,?,?)",
                (memory_id, session_id, content, created_at, meta_json),
            )
            # Get the rowid just inserted
            async with db.execute(
                "SELECT rowid FROM memory_vectors WHERE id = ?", (memory_id,)
            ) as cur:
                row = await cur.fetchone()
            
            if not row:
                raise RuntimeError("Failed to retrieve rowid for inserted memory")
            rowid = row[0]

            # Update rowid_key
            await db.execute(
                "UPDATE memory_vectors SET rowid_key = ? WHERE id = ?",
                (rowid, memory_id),
            )

            # Insert into vec0 virtual table
            serialized = sqlite_vec.serialize_float32(embedding)
            await db.execute(
                "INSERT INTO memory_vec(rowid, embedding) VALUES (?, ?)",
                (rowid, serialized),
            )

            # Insert into FTS
            await db.execute(
                "INSERT INTO memory_fts(memory_id, content) VALUES (?,?)",
                (memory_id, content),
            )
            await db.commit()

        return memory_id

    async def vector_search(
        self, query_emb: list[float], session_id: str | None, limit: int
    ) -> list[dict]:
        """KNN vector search via vec0."""
        serialized = sqlite_vec.serialize_float32(query_emb)

        async with aiosqlite.connect(self.db_path) as db:
            await db.enable_load_extension(True)
            await db.load_extension(sqlite_vec.loadable_path())
            db.row_factory = aiosqlite.Row

            # KNN via vec0 MATCH syntax
            sql = """
                SELECT mv.id, mv.content, mv.created_at, v.distance
                FROM memory_vec v
                JOIN memory_vectors mv ON v.rowid = mv.rowid_key
                WHERE v.embedding MATCH ? AND k = ?
                ORDER BY v.distance
            """
            params: list = [serialized, limit * 3]

            async with db.execute(sql, params) as cur:
                rows = await cur.fetchall()

        results = []
        for r in rows:
            if session_id and (
                # filter by session_id after KNN (or re-query)
                not (await self._row_matches_session(r["id"], session_id))
            ):
                continue
            results.append({
                "id": r["id"],
                "content": r["content"],
                "created_at": r["created_at"],
                "score": max(0.0, 1.0 - r["distance"]),
            })

        return results[:limit]

    async def _row_matches_session(self, memory_id: str, session_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT 1 FROM memory_vectors WHERE id = ? AND session_id = ?",
                (memory_id, session_id),
            ) as cur:
                return await cur.fetchone() is not None

    async def fts_search(
        self, query: str, session_id: str | None, limit: int
    ) -> list[dict]:
        """BM25 full-text search."""
        import re
        # Skip FTS entirely for non-ASCII queries (Chinese etc.) — vector search handles them
        if not query.isascii():
            return []
        # Sanitize to remove FTS5 special chars (dots, dashes, operators)
        query = re.sub(r'[<>()@\[\]*^",:?!.\-]', ' ', query).strip()
        if not query:
            return []

        sql = """
            SELECT f.memory_id as id, v.content, v.created_at, (-f.rank) as score
            FROM memory_fts f
            JOIN memory_vectors v ON f.memory_id = v.id
            WHERE memory_fts MATCH ?
        """
        params: list = [query]
        if session_id:
            sql += " AND v.session_id = ?"
            params.append(session_id)
        sql += " ORDER BY f.rank LIMIT ?"
        params.append(limit)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, params) as cur:
                rows = await cur.fetchall()

        return [
            {
                "id": r["id"],
                "content": r["content"],
                "created_at": r["created_at"],
                "score": float(r["score"]),
            }
            for r in rows
        ]

    async def delete(self, memory_id: str) -> None:
        self.clear_cache()
        async with aiosqlite.connect(self.db_path) as db:
            await db.enable_load_extension(True)
            await db.load_extension(sqlite_vec.loadable_path())

            # Get rowid first
            async with db.execute(
                "SELECT rowid_key FROM memory_vectors WHERE id = ?", (memory_id,)
            ) as cur:
                row = await cur.fetchone()

            if row:
                rowid = row[0]
                await db.execute("DELETE FROM memory_vec WHERE rowid = ?", (rowid,))

            await db.execute("DELETE FROM memory_vectors WHERE id = ?", (memory_id,))
            await db.execute("DELETE FROM memory_fts WHERE memory_id = ?", (memory_id,))
            await db.commit()
