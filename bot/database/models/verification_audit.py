# bot/database/models/verification_audit.py
"""
VerificationAudit model (matches table: verification_audit)
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Literal


ResultType = Literal["success", "failure"]


@dataclass
class VerificationAudit:
    id: Optional[int]
    discord_id: int
    login: str
    cas_username: str
    state_sha256: str
    ticket_sha256: str
    result: ResultType
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict) -> "VerificationAudit":
        return cls(
            id=row.get("id"),
            discord_id=row["discord_id"],
            login=row["login"],
            cas_username=row["cas_username"],
            state_sha256=row["state_sha256"],
            ticket_sha256=row["ticket_sha256"],
            result=row["result"],
            error_message=row.get("error_message"),
            created_at=row.get("created_at"),
        )
