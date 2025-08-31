# bot/database/queries/verification_audit_queries.py
"""
Queries for verification_audit
"""
import hashlib
import asyncpg
from ..models.verification_audit import VerificationAudit, ResultType


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class VerificationAuditQueries:
    def __init__(self, db_pool: asyncpg.Pool):
        self.pool = db_pool

    async def insert(
        self,
        discord_id: str,
        login: str,
        cas_username: str,
        state_plaintext: str,
        ticket_plaintext: str,
        result: ResultType,
        error_message: str | None = None,
    ) -> int:
        sql = """
        INSERT INTO verification_audit (
            discord_id, login, cas_username, state_sha256, ticket_sha256, result, error_message, created_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,NOW())
        RETURNING id
        """
        state_sha = _sha256_hex(state_plaintext)
        ticket_sha = _sha256_hex(ticket_plaintext)

        async with self.pool.acquire() as conn:
            new_id = await conn.fetchval(
                sql,
                discord_id,
                login,
                cas_username,
                state_sha,
                ticket_sha,
                result,
                error_message,
            )
            return int(new_id)

    async def recent_for_user(self, discord_id: str, limit: int = 20) -> list[VerificationAudit]:
        sql = """
        SELECT * FROM verification_audit
        WHERE discord_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, discord_id, limit)
            return [VerificationAudit.from_row(dict(r)) for r in rows]
