# bot/database/queries/shame_queries.py
from __future__ import annotations
from typing import Any
import asyncpg


class ShameQueries:
    @staticmethod
    async def ensure_schema(pool: asyncpg.Pool) -> None:
        async with pool.acquire() as conn:
            await conn.execute(
                """
            CREATE TABLE IF NOT EXISTS shame_stats(
              user_id BIGINT PRIMARY KEY,
              warnings INT NOT NULL DEFAULT 0,
              kicks INT NOT NULL DEFAULT 0,
              bans INT NOT NULL DEFAULT 0,
              timeouts INT NOT NULL DEFAULT 0,
              last_event_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
            )
            await conn.execute(
                """
            CREATE TABLE IF NOT EXISTS shame_events(
              id BIGSERIAL PRIMARY KEY,
              user_id BIGINT NOT NULL,
              kind TEXT NOT NULL,
              reason TEXT,
              at TIMESTAMPTZ NOT NULL DEFAULT now(),
              moderator_id BIGINT
            );
            """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_shame_user_at ON shame_events(user_id, at desc);"
            )

    @staticmethod
    async def _ensure_row(conn: asyncpg.Connection, user_id: int) -> None:
        """Ensure user exists in shame_stats. user_id must be int."""
        await conn.execute(
            "INSERT INTO shame_stats(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING", 
            user_id
        )

    @staticmethod
    async def add_event(
        pool: asyncpg.Pool, *, 
        user_id: int,  # Must be int
        kind: str, 
        reason: str | None, 
        moderator_id: int | None  # Must be int
    ) -> None:
        """Add shame event. user_id and moderator_id must be int."""
        kind = kind if kind in ("warn", "kick", "ban", "timeout") else "warn"
        col = {"warn": "warnings", "kick": "kicks", "ban": "bans", "timeout": "timeouts"}[kind]
        
        async with pool.acquire() as conn:
            await ShameQueries._ensure_row(conn, user_id)
            await conn.execute(
                f"""
            UPDATE shame_stats SET {col} = {col} + 1, last_event_at = now() WHERE user_id=$1
            """,
                user_id,
            )
            await conn.execute(
                """
            INSERT INTO shame_events(user_id, kind, reason, at, moderator_id)
            VALUES ($1,$2,$3,now(),$4)
            """,
                user_id,
                kind,
                reason,
                moderator_id,
            )

    @staticmethod
    async def get_stats(pool: asyncpg.Pool, user_id: int) -> dict[str, Any] | None:
        """Get user shame stats. user_id must be int."""
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM shame_stats WHERE user_id=$1", user_id)
        return dict(row) if row else None