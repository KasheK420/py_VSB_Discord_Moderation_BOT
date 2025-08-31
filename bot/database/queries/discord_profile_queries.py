# bot/database/queries/discord_profile_queries.py
"""
Queries for discord_profiles
"""
import asyncpg
from ..models.discord_profile import DiscordProfile


class DiscordProfileQueries:
    def __init__(self, db_pool: asyncpg.Pool):
        self.pool = db_pool

    async def get(self, discord_id: str) -> DiscordProfile | None:
        sql = "SELECT * FROM discord_profiles WHERE discord_id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, discord_id)
            return DiscordProfile.from_row(dict(row)) if row else None

    async def upsert(self, profile: DiscordProfile) -> None:
        sql = """
        INSERT INTO discord_profiles (
            discord_id, username, global_name, discriminator, locale, country_code,
            account_created_at, account_age_days, is_bot, avatar_hash, created_at, updated_at
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NOW(),NOW()
        )
        ON CONFLICT (discord_id) DO UPDATE SET
            username = EXCLUDED.username,
            global_name = EXCLUDED.global_name,
            discriminator = EXCLUDED.discriminator,
            locale = EXCLUDED.locale,
            country_code = EXCLUDED.country_code,
            account_created_at = EXCLUDED.account_created_at,
            account_age_days = EXCLUDED.account_age_days,
            is_bot = EXCLUDED.is_bot,
            avatar_hash = EXCLUDED.avatar_hash,
            updated_at = NOW()
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                sql,
                profile.discord_id,
                profile.username,
                profile.global_name,
                profile.discriminator,
                profile.locale,
                profile.country_code,
                profile.account_created_at,
                profile.account_age_days,
                profile.is_bot,
                profile.avatar_hash,
            )
