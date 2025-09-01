# bot/database/queries/discord_stats_queries.py
"""
Queries for discord_user_stats
"""

from __future__ import annotations

import asyncpg
from typing import Optional

from ..models.discord_user_stats import DiscordUserStats


class DiscordStatsQueries:
    def __init__(self, db_pool: asyncpg.Pool):
        self.pool = db_pool

    async def get(self, discord_id: int) -> Optional[DiscordUserStats]:
        sql = "SELECT * FROM discord_user_stats WHERE discord_id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, discord_id)
            return DiscordUserStats.from_row(dict(row)) if row else None

    async def ensure_row(self, discord_id: int) -> None:
        sql = """
        INSERT INTO discord_user_stats (discord_id)
        VALUES ($1)
        ON CONFLICT (discord_id) DO NOTHING
        """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, discord_id)

    async def touch_seen(
        self,
        discord_id: int,
        last_login_ip: Optional[str] = None,
        increment_login: bool = True,
    ) -> None:
        """
        Upsert last_seen and optionally increment login_count.
        """
        if increment_login:
            sql = """
            INSERT INTO discord_user_stats (discord_id, first_seen_at, last_seen_at, login_count, last_login_ip)
            VALUES ($1, NOW(), NOW(), 1, $2::inet)
            ON CONFLICT (discord_id) DO UPDATE SET
                last_seen_at = NOW(),
                login_count = discord_user_stats.login_count + 1,
                last_login_ip = COALESCE($2::inet, discord_user_stats.last_login_ip)
            """
        else:
            sql = """
            INSERT INTO discord_user_stats (discord_id, first_seen_at, last_seen_at, last_login_ip)
            VALUES ($1, NOW(), NOW(), $2::inet)
            ON CONFLICT (discord_id) DO UPDATE SET
                last_seen_at = NOW(),
                last_login_ip = COALESCE($2::inet, discord_user_stats.last_login_ip)
            """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, discord_id, last_login_ip)

    async def inc_message_count(self, discord_id: int, by: int = 1) -> None:
        sql = """
        INSERT INTO discord_user_stats (discord_id, message_count)
        VALUES ($1, $2)
        ON CONFLICT (discord_id) DO UPDATE SET
            message_count = discord_user_stats.message_count + EXCLUDED.message_count
        """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, discord_id, by)

    async def inc_join_count(self, discord_id: int, by: int = 1) -> None:
        sql = """
        INSERT INTO discord_user_stats (discord_id, join_count)
        VALUES ($1, $2)
        ON CONFLICT (discord_id) DO UPDATE SET
            join_count = discord_user_stats.join_count + EXCLUDED.join_count
        """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, discord_id, by)

    async def add_voice_minutes(self, discord_id: int, minutes: int) -> None:
        """
        Optional helper to accumulate voice activity minutes.
        Safe if column exists; no-op otherwise.
        """
        sql = """
        INSERT INTO discord_user_stats (discord_id, voice_minutes)
        VALUES ($1, $2)
        ON CONFLICT (discord_id) DO UPDATE SET
            voice_minutes = COALESCE(discord_user_stats.voice_minutes, 0) + EXCLUDED.voice_minutes
        """
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(sql, discord_id, minutes)
            except asyncpg.UndefinedColumnError:
                # Column not present in schema; skip silently
                pass
