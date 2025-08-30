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
              kind TEXT NOT NULL,  -- 'warn'|'kick'|'ban'|'timeout'
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
        await conn.execute(
            "INSERT INTO shame_stats(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING", user_id
        )

    @staticmethod
    async def add_event(
        pool: asyncpg.Pool, *, user_id: int, kind: str, reason: str | None, moderator_id: int | None
    ) -> None:
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
            INSERT INTO shame_events(user_id,kind,reason,moderator_id)
            VALUES ($1,$2,$3,$4)
            """,
                user_id,
                kind,
                reason,
                moderator_id,
            )

    @staticmethod
    async def stats(pool: asyncpg.Pool, user_id: int) -> dict[str, Any] | None:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM shame_stats WHERE user_id=$1", user_id)
        return dict(row) if row else None

    @staticmethod
    async def leaderboard(
        pool: asyncpg.Pool, by: str = "warnings", limit: int = 10
    ) -> list[dict[str, Any]]:
        by = by if by in ("warnings", "kicks", "bans", "timeouts") else "warnings"
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
            SELECT user_id,warnings,kicks,bans,timeouts,last_event_at
              FROM shame_stats
             ORDER BY {by} DESC, last_event_at DESC
             LIMIT $1
            """,
                limit,
            )
        return [dict(r) for r in rows]
