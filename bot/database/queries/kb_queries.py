# bot/database/queries/kb_queries.py
from __future__ import annotations

from typing import Any

import asyncpg

from ..models.kb import KBArticle


class KBQueries:
    """
    KB queries using asyncpg. Includes schema bootstrap (extensions, tables, indexes, trigger).
    Uses an IMMUTABLE wrapper around unaccent() to satisfy index-expression requirements.
    """

    # ---------- schema bootstrap ----------

    @staticmethod
    async def ensure_schema(pool: asyncpg.Pool) -> None:
        """Create extensions, functions, tables, indexes if they do not exist."""
        async with pool.acquire() as conn:
            # Extensions
            await conn.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

            # IMMUTABLE wrapper for unaccent() so it can be used inside index expressions safely
            # (Some environments complain about direct unaccent() in expression indexes.)
            await conn.execute(
                """
                CREATE OR REPLACE FUNCTION immutable_unaccent(text)
                RETURNS text
                LANGUAGE sql
                IMMUTABLE
                PARALLEL SAFE
                AS $$ SELECT public.unaccent($1) $$;
                """
            )

            # Tables
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kb_articles (
                  id           BIGSERIAL PRIMARY KEY,
                  title        TEXT NOT NULL,
                  url          TEXT,
                  category     TEXT,
                  body         TEXT NOT NULL,
                  tags         TEXT[] DEFAULT '{}',
                  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  content_fts  tsvector
                );
                """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kb_auto_replies (
                  thread_id       BIGINT PRIMARY KEY,
                  post_message_id BIGINT NOT NULL,
                  kb_ids          BIGINT[] NOT NULL,
                  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kb_feedback (
                  thread_id BIGINT NOT NULL,
                  user_id   BIGINT NOT NULL,
                  helpful   BOOLEAN NOT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  PRIMARY KEY(thread_id, user_id)
                );
                """
            )

            # Trigger function to keep FTS up to date (use IMMUTABLE wrapper)
            await conn.execute(
                """
                CREATE OR REPLACE FUNCTION kb_articles_fts_trigger() RETURNS trigger AS $$
                BEGIN
                  NEW.content_fts :=
                    to_tsvector(
                      'simple',
                      immutable_unaccent(coalesce(NEW.title,'') || ' ' ||
                                         coalesce(NEW.body,'')  || ' ' ||
                                         coalesce(array_to_string(NEW.tags, ' '),''))
                    );
                  RETURN NEW;
                END
                $$ LANGUAGE plpgsql;
                """
            )

            await conn.execute("DROP TRIGGER IF EXISTS kb_articles_fts_tg ON kb_articles;")
            await conn.execute(
                """
                CREATE TRIGGER kb_articles_fts_tg
                  BEFORE INSERT OR UPDATE ON kb_articles
                  FOR EACH ROW EXECUTE FUNCTION kb_articles_fts_trigger();
                """
            )

            # Indexes
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kb_articles_fts ON kb_articles USING GIN (content_fts);"
            )

            # Re-create trigram indexes using the IMMUTABLE wrapper to avoid 'must be IMMUTABLE' errors
            await conn.execute("DROP INDEX IF EXISTS idx_kb_articles_title_trgm;")
            await conn.execute("DROP INDEX IF EXISTS idx_kb_articles_body_trgm;")
            await conn.execute(
                "CREATE INDEX idx_kb_articles_title_trgm ON kb_articles USING GIN (immutable_unaccent(title) gin_trgm_ops);"
            )
            await conn.execute(
                "CREATE INDEX idx_kb_articles_body_trgm ON kb_articles USING GIN (immutable_unaccent(body) gin_trgm_ops);"
            )

            # Backfill FTS for any existing rows (fire the BEFORE UPDATE trigger on all rows)
            await conn.execute("UPDATE kb_articles SET updated_at = updated_at;")

    # ---------- CRUD: articles ----------

    @staticmethod
    async def upsert_article(
        pool: asyncpg.Pool,
        *,
        title: str,
        body: str,
        url: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        article_id: int | None = None,
    ) -> int:
        tags = tags or []
        async with pool.acquire() as conn:
            if article_id:
                row = await conn.fetchrow(
                    """
                    UPDATE kb_articles
                       SET title = $1,
                           url = $2,
                           category = $3,
                           body = $4,
                           tags = $5,
                           updated_at = NOW()
                     WHERE id = $6
                     RETURNING id
                    """,
                    title,
                    url,
                    category,
                    body,
                    tags,
                    article_id,
                )
            else:
                row = await conn.fetchrow(
                    """
                    INSERT INTO kb_articles (title, url, category, body, tags)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                    """,
                    title,
                    url,
                    category,
                    body,
                    tags,
                )
        return int(row["id"])

    @staticmethod
    async def get_article(pool: asyncpg.Pool, article_id: int) -> KBArticle | None:
        async with pool.acquire() as conn:
            r = await conn.fetchrow("SELECT * FROM kb_articles WHERE id = $1", article_id)
        if not r:
            return None
        return KBArticle(
            id=int(r["id"]),
            title=r["title"],
            body=r["body"],
            url=r["url"],
            category=r["category"],
            tags=list(r["tags"] or []),
        )

    @staticmethod
    async def list_articles(
        pool: asyncpg.Pool, limit: int = 50, offset: int = 0
    ) -> list[KBArticle]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM kb_articles ORDER BY updated_at DESC LIMIT $1 OFFSET $2",
                limit,
                offset,
            )
        return [
            KBArticle(
                id=int(r["id"]),
                title=r["title"],
                body=r["body"],
                url=r["url"],
                category=r["category"],
                tags=list(r["tags"] or []),
            )
            for r in rows
        ]

    @staticmethod
    async def delete_article(pool: asyncpg.Pool, article_id: int) -> bool:
        async with pool.acquire() as conn:
            res = await conn.execute("DELETE FROM kb_articles WHERE id = $1", article_id)
        return res.upper().startswith("DELETE")

    # ---------- SEARCH ----------

    @staticmethod
    async def search(
        pool: asyncpg.Pool,
        query: str,
        *,
        limit: int = 5,
        min_rank: float = 0.02,
        min_trgm: float = 0.15,
    ) -> list[dict[str, Any]]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH q AS (
                    SELECT
                        to_tsquery('simple', immutable_unaccent(regexp_replace($1, '\s+', ' & ', 'g'))) AS ts,
                        immutable_unaccent($1) AS uq
                )
                SELECT
                    a.id, a.title, a.url, a.category,
                    ts_rank_cd(a.content_fts, q.ts) AS rank,
                    greatest(similarity(immutable_unaccent(a.title), q.uq),
                             similarity(immutable_unaccent(a.body),  q.uq)) AS sim,
                    left(a.body, 250) AS snippet
                FROM kb_articles a, q
                WHERE a.content_fts @@ q.ts
                   OR immutable_unaccent(a.title) % q.uq
                   OR immutable_unaccent(a.body)  % q.uq
                ORDER BY (ts_rank_cd(a.content_fts, q.ts) * 0.7
                         + greatest(similarity(immutable_unaccent(a.title), q.uq),
                                    similarity(immutable_unaccent(a.body), q.uq)) * 0.3) DESC
                LIMIT $2
                """,
                query,
                limit,
            )

        out: list[dict[str, Any]] = []
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

    # ---------- auto-replies & feedback ----------

    @staticmethod
    async def mark_replied(
        pool: asyncpg.Pool, thread_id: int, post_message_id: int, kb_ids: list[int]
    ) -> None:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO kb_auto_replies(thread_id, post_message_id, kb_ids)
                VALUES ($1, $2, $3)
                ON CONFLICT (thread_id) DO UPDATE
                SET kb_ids = excluded.kb_ids, updated_at = NOW()
                """,
                thread_id,
                post_message_id,
                kb_ids,
            )

    @staticmethod
    async def was_replied(pool: asyncpg.Pool, thread_id: int) -> bool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM kb_auto_replies WHERE thread_id = $1", thread_id
            )
        return bool(row)

    @staticmethod
    async def record_feedback(
        pool: asyncpg.Pool, thread_id: int, helpful: bool, user_id: int
    ) -> None:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO kb_feedback(thread_id, user_id, helpful)
                VALUES ($1, $2, $3)
                ON CONFLICT (thread_id, user_id) DO UPDATE
                SET helpful = excluded.helpful, updated_at = NOW()
                """,
                thread_id,
                user_id,
                helpful,
            )
