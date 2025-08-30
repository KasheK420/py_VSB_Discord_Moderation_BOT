# bot/database/queries/hof_queries.py
from __future__ import annotations

import asyncpg


class HOFQueries:
    @staticmethod
    async def ensure_schema(pool: asyncpg.Pool) -> None:
        async with pool.acquire() as conn:
            await conn.execute(
                """
            CREATE TABLE IF NOT EXISTS hall_of_fame_posts(
              message_id BIGINT PRIMARY KEY,
              channel_id BIGINT NOT NULL,
              author_id BIGINT NOT NULL,
              posted_in BIGINT NOT NULL,
              fame_message_id BIGINT NOT NULL,
              reaction_total INT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_hof_author ON hall_of_fame_posts(author_id);"
            )

    @staticmethod
    async def was_posted(pool: asyncpg.Pool, message_id: int) -> bool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM hall_of_fame_posts WHERE message_id=$1", message_id
            )
        return bool(row)

    @staticmethod
    async def record_post(
        pool: asyncpg.Pool,
        *,
        message_id: int,
        channel_id: int,
        author_id: int,
        posted_in: int,
        fame_message_id: int,
        reaction_total: int,
    ) -> None:
        async with pool.acquire() as conn:
            await conn.execute(
                """
            INSERT INTO hall_of_fame_posts(message_id,channel_id,author_id,posted_in,fame_message_id,reaction_total)
            VALUES ($1,$2,$3,$4,$5,$6)
            ON CONFLICT (message_id) DO NOTHING
            """,
                message_id,
                channel_id,
                author_id,
                posted_in,
                fame_message_id,
                reaction_total,
            )
