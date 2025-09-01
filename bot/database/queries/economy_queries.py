# bot/database/queries/economy_queries.py
from __future__ import annotations
from typing import Any
import asyncpg


class EconomyQueries:
    @staticmethod
    async def ensure_schema(pool: asyncpg.Pool) -> None:
        async with pool.acquire() as conn:
            await conn.execute(
                """
            CREATE TABLE IF NOT EXISTS xp_stats(
              user_id BIGINT PRIMARY KEY,
              xp BIGINT NOT NULL DEFAULT 0,
              points BIGINT NOT NULL DEFAULT 0,
              level INT NOT NULL DEFAULT 1,
              messages BIGINT NOT NULL DEFAULT 0,
              reactions_received BIGINT NOT NULL DEFAULT 0,
              daily_xp BIGINT NOT NULL DEFAULT 0,
              daily_xp_date DATE NOT NULL DEFAULT CURRENT_DATE,
              last_updated TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
            )
            await conn.execute(
                """
            CREATE TABLE IF NOT EXISTS xp_events(
              id BIGSERIAL PRIMARY KEY,
              user_id BIGINT NOT NULL,
              kind TEXT NOT NULL,
              delta_xp INT NOT NULL,
              delta_points INT NOT NULL,
              meta TEXT,
              at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_xp_events_user_at ON xp_events(user_id, at desc);"
            )

    @staticmethod
    async def _ensure_row(conn: asyncpg.Connection, user_id: int) -> None:
        """Ensure user exists in xp_stats table."""
        await conn.execute(
            """
        INSERT INTO xp_stats(user_id, daily_xp, daily_xp_date) 
        VALUES($1, 0, CURRENT_DATE)
        ON CONFLICT (user_id) DO NOTHING
        """,
            user_id,
        )

    @staticmethod
    async def add_message_xp(pool: asyncpg.Pool, user_id: int, xp: int, points: int) -> None:
        """Add XP and points for a message. user_id must be int."""
        async with pool.acquire() as conn:
            await EconomyQueries._ensure_row(conn, user_id)
            await conn.execute(
                """
            UPDATE xp_stats
               SET xp = xp + $2,
                   points = points + $3,
                   messages = messages + 1,
                   daily_xp = CASE WHEN daily_xp_date = CURRENT_DATE THEN daily_xp + $2 ELSE $2 END,
                   daily_xp_date = CURRENT_DATE,
                   last_updated = now()
             WHERE user_id = $1
            """,
                user_id,
                xp,
                points,
            )
            await conn.execute(
                """
            INSERT INTO xp_events(user_id, kind, delta_xp, delta_points, meta)
            VALUES ($1,'message',$2,$3,NULL)
            """,
                user_id,
                xp,
                points,
            )

    @staticmethod
    async def add_reaction_received(
        pool: asyncpg.Pool, user_id: int, xp: int, points: int, meta: str
    ) -> None:
        """Add XP for reaction received. user_id must be int."""
        async with pool.acquire() as conn:
            await EconomyQueries._ensure_row(conn, user_id)
            await conn.execute(
                """
            UPDATE xp_stats
               SET xp = xp + $2,
                   points = points + $3,
                   reactions_received = reactions_received + 1,
                   daily_xp = CASE WHEN daily_xp_date = CURRENT_DATE THEN daily_xp + $2 ELSE $2 END,
                   daily_xp_date = CURRENT_DATE,
                   last_updated = now()
             WHERE user_id = $1
            """,
                user_id,
                xp,
                points,
            )
            await conn.execute(
                """
            INSERT INTO xp_events(user_id, kind, delta_xp, delta_points, meta)
            VALUES ($1,'reaction_received',$2,$3,$4)
            """,
                user_id,
                xp,
                points,
                meta,
            )

    @staticmethod
    async def get_stats(pool: asyncpg.Pool, user_id: int) -> dict[str, Any] | None:
        """Get user stats. user_id must be int."""
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM xp_stats WHERE user_id=$1", user_id)
        return dict(row) if row else None

    @staticmethod
    async def adjust_points(
        pool: asyncpg.Pool,
        user_id: int,
        delta_points: int,
        *,
        delta_xp: int = 0,
        meta: str = "adjust",
    ) -> dict[str, Any]:
        """Atomic points adjustment. user_id must be int."""
        async with pool.acquire() as conn:
            async with conn.transaction():
                await EconomyQueries._ensure_row(conn, user_id)
                row = await conn.fetchrow(
                    "SELECT points FROM xp_stats WHERE user_id=$1 FOR UPDATE", user_id
                )
                new_points = int(row["points"]) + int(delta_points)
                if new_points < 0:
                    raise ValueError("Insufficient points")
                await conn.execute(
                    """
                UPDATE xp_stats
                   SET points = points + $2,
                       xp = xp + $3,
                       last_updated = now()
                 WHERE user_id = $1
                """,
                    user_id,
                    delta_points,
                    delta_xp,
                )
                await conn.execute(
                    """
                INSERT INTO xp_events(user_id, kind, delta_xp, delta_points, meta)
                VALUES ($1,'admin_adjust',$2,$3,$4)
                """,
                    user_id,
                    delta_xp,
                    delta_points,
                    meta,
                )
                out = await conn.fetchrow("SELECT * FROM xp_stats WHERE user_id=$1", user_id)
                return dict(out)

    @staticmethod
    async def spend_points(
        pool: asyncpg.Pool, user_id: int, amount: int, *, meta: str
    ) -> dict[str, Any]:
        """Spend points. user_id must be int."""
        if amount <= 0:
            raise ValueError("Amount must be > 0")
        return await EconomyQueries.adjust_points(pool, user_id, -amount, delta_xp=0, meta=meta)

    @staticmethod
    async def award_points(
        pool: asyncpg.Pool, user_id: int, amount: int, *, meta: str
    ) -> dict[str, Any]:
        """Award points. user_id must be int."""
        if amount <= 0:
            return await EconomyQueries.get_stats(pool, user_id) or {
                "user_id": user_id,
                "points": 0,
            }
        return await EconomyQueries.adjust_points(pool, user_id, amount, delta_xp=0, meta=meta)

    @staticmethod
    async def leaderboard(
        pool: asyncpg.Pool, by: str = "xp", limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get leaderboard. Returns list with user_id as BIGINT."""
        by = by if by in ("xp", "points", "messages", "reactions_received") else "xp"
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
            SELECT user_id, xp, points, messages, reactions_received, level
            FROM xp_stats
            ORDER BY {by} DESC
            LIMIT $1
            """,
                limit,
            )
        return [dict(r) for r in rows]