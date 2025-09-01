# bot/database/queries/cas_attributes_history_queries.py
"""
Queries for cas_attributes_history
"""
import json
import asyncpg
from ..models.cas_attributes_history import CASAttributesHistory


class CASAttributesHistoryQueries:
    def __init__(self, db_pool: asyncpg.Pool):
        self.pool = db_pool

    async def insert_snapshot(self, discord_id: int, login: str, attributes: dict) -> int:
        sql = """
        INSERT INTO cas_attributes_history (discord_id, login, attributes, received_at)
        VALUES ($1, $2, $3::jsonb, NOW())
        RETURNING id
        """
        async with self.pool.acquire() as conn:
            new_id = await conn.fetchval(sql, discord_id, login, json.dumps(attributes))
            return int(new_id)

    async def recent_for_user(self, discord_id: int, limit: int = 20) -> list[CASAttributesHistory]:
        sql = """
        SELECT * FROM cas_attributes_history
        WHERE discord_id = $1
        ORDER BY received_at DESC
        LIMIT $2
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, discord_id, limit)
            return [CASAttributesHistory.from_row(dict(r)) for r in rows]
