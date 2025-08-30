# bot/services/kb_service.py
"""
KBService: Manage a lightweight knowledge base and perform fast PostgreSQL FTS retrieval.
- No embeddings required; uses to_tsvector + unaccent + trigram similarity for multi-language.
- Works great for CZ/PL/EN docs when unaccent + 'simple' config are used.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class KBArticle:
    id: int
    title: str
    url: Optional[str]
    category: Optional[str]
    body: str
    tags: List[str]


class KBService:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    # ---------- CRUD ----------

    async def upsert_article(
        self,
        *,
        title: str,
        body: str,
        url: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        article_id: Optional[int] = None,
    ) -> int:
        """Insert or update a KB article. Returns the article id."""
        tags = tags or []
        async with self.pool.acquire() as conn:
            if article_id:
                q = """
                update kb_articles
                   set title = $1,
                       url = $2,
                       category = $3,
                       body = $4,
                       tags = $5,
                       updated_at = now(),
                       content_fts = to_tsvector('simple', unaccent($1 || ' ' || $4 || ' ' || coalesce(array_to_string($5, ' '), '')))
                 where id = $6
                 returning id
                """
                row = await conn.fetchrow(q, title, url, category, body, tags, article_id)
            else:
                q = """
                insert into kb_articles (title, url, category, body, tags, content_fts)
                values ($1, $2, $3, $4, $5,
                        to_tsvector('simple', unaccent($1 || ' ' || $4 || ' ' || coalesce(array_to_string($5, ' '), '')))
                       )
                returning id
                """
                row = await conn.fetchrow(q, title, url, category, body, tags)
        return int(row["id"])

    async def get_article(self, article_id: int) -> Optional[KBArticle]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("select * from kb_articles where id = $1", article_id)
        if not row:
            return None
        return KBArticle(
            id=row["id"],
            title=row["title"],
            url=row["url"],
            category=row["category"],
            body=row["body"],
            tags=list(row["tags"] or []),
        )

    async def list_articles(self, limit: int = 50, offset: int = 0) -> List[KBArticle]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "select * from kb_articles order by updated_at desc limit $1 offset $2", limit, offset
            )
        return [
            KBArticle(
                id=r["id"],
                title=r["title"],
                url=r["url"],
                category=r["category"],
                body=r["body"],
                tags=list(r["tags"] or []),
            )
            for r in rows
        ]

    async def delete_article(self, article_id: int) -> bool:
        async with self.pool.acquire() as conn:
            r = await conn.execute("delete from kb_articles where id = $1", article_id)
        return r and r.upper().startswith("DELETE")

    # ---------- SEARCH ----------

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        min_rank: float = 0.02,
        min_trgm: float = 0.15,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search:
          1) Full-text rank on 'simple' + unaccent.
          2) Trigram similarity to tolerate typos/inflections.
        Returns: [{id, title, url, category, snippet, rank, similarity}]
        """
        # plainto_tsquery works reasonably for multi-language with 'simple'
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                with q as (
                    select
                        to_tsquery('simple', unaccent(regexp_replace($1, '\s+', ' & ', 'g'))) as ts,
                        unaccent($1) as uq
                )
                select
                    a.id, a.title, a.url, a.category,
                    ts_rank_cd(a.content_fts, q.ts) as rank,
                    greatest(similarity(unaccent(a.title), q.uq),
                             similarity(unaccent(a.body),  q.uq)) as sim,
                    -- simple snippet (first 250 chars)
                    left(a.body, 250) as snippet
                from kb_articles a, q
                where a.content_fts @@ q.ts
                   or unaccent(a.title) % q.uq
                   or unaccent(a.body)  % q.uq
                order by (ts_rank_cd(a.content_fts, q.ts) * 0.7 + greatest(similarity(unaccent(a.title), q.uq), similarity(unaccent(a.body), q.uq)) * 0.3) desc
                limit $2
                """,
                query,
                limit,
            )

        out = []
        for r in rows:
            rank = float(r["rank"] or 0.0)
            sim = float(r["sim"] or 0.0)
            if rank < min_rank and sim < min_trgm:
                continue
            out.append(
                {
                    "id": int(r["id"]),
                    "title": r["title"],
                    "url": r["url"],
                    "category": r["category"],
                    "rank": rank,
                    "similarity": sim,
                    "snippet": r["snippet"],
                }
            )
        return out

    # ---------- Auto-replies bookkeeping ----------

    async def mark_replied(self, thread_id: int, post_message_id: int, kb_ids: List[int]) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                insert into kb_auto_replies(thread_id, post_message_id, kb_ids)
                values ($1, $2, $3)
                on conflict (thread_id) do update
                set kb_ids = excluded.kb_ids, updated_at = now()
                """,
                thread_id,
                post_message_id,
                kb_ids,
            )

    async def was_replied(self, thread_id: int) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("select 1 from kb_auto_replies where thread_id = $1", thread_id)
        return bool(row)

    async def record_feedback(self, thread_id: int, helpful: bool, user_id: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                insert into kb_feedback(thread_id, user_id, helpful)
                values ($1, $2, $3)
                on conflict (thread_id, user_id) do update
                set helpful = excluded.helpful, updated_at = now()
                """,
                thread_id,
                user_id,
                helpful,
            )
