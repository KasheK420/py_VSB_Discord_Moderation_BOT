# bot/database/models/discord_user_stats.py
"""
DiscordUserStats model (matches table: discord_user_stats)
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class DiscordUserStats:
    discord_id: int   
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    login_count: int = 0
    message_count: int = 0
    join_count: int = 0
    last_login_ip: Optional[str] = None  # INET

    @classmethod
    def from_row(cls, row: dict) -> "DiscordUserStats":
        return cls(
            discord_id=row["discord_id"],
            first_seen_at=row.get("first_seen_at"),
            last_seen_at=row.get("last_seen_at"),
            login_count=row.get("login_count", 0),
            message_count=row.get("message_count", 0),
            join_count=row.get("join_count", 0),
            last_login_ip=row.get("last_login_ip"),
        )
