"""
bot/database/queries/poll_queries.py
Poll-related database queries for PostgreSQL
"""

import asyncpg

from ..models.poll import Poll


class PollQueries:
    def __init__(self, db_pool: asyncpg.Pool):
        self.pool = db_pool

    async def create_poll(self, poll: Poll) -> None:
        """Create a new poll"""
        query = """
            INSERT INTO polls (
                id, start, "end", author, type, title, options, emojis, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                poll.id,
                poll.start,
                poll.end,
                poll.author,
                poll.type,
                poll.title,
                poll.options,
                poll.emojis,
            )

    async def get_poll_by_id(self, poll_id: str) -> Poll | None:
        """Get poll by ID"""
        query = """
            SELECT * FROM polls WHERE id = $1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, poll_id)
            return Poll.from_row(dict(row)) if row else None

    async def get_active_polls(self) -> list[Poll]:
        """Get all active polls"""
        query = """
            SELECT * FROM polls 
            WHERE "end" > NOW()
            ORDER BY start DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [Poll.from_row(dict(row)) for row in rows]
