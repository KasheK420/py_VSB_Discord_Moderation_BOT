# bot/database/models/discord_profile.py
"""
DiscordProfile model (matches table: discord_profiles)
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class DiscordProfile:
    discord_id: str
    username: str
    global_name: Optional[str] = None
    discriminator: Optional[str] = None
    locale: Optional[str] = None
    country_code: Optional[str] = None  # 2-letter country code
    account_created_at: Optional[datetime] = None
    account_age_days: Optional[float] = None
    is_bot: bool = False
    avatar_hash: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict) -> "DiscordProfile":
        return cls(
            discord_id=row["discord_id"],
            username=row["username"],
            global_name=row.get("global_name"),
            discriminator=row.get("discriminator"),
            locale=row.get("locale"),
            country_code=row.get("country_code"),
            account_created_at=row.get("account_created_at"),
            account_age_days=float(row["account_age_days"]) if row.get("account_age_days") is not None else None,
            is_bot=row.get("is_bot", False),
            avatar_hash=row.get("avatar_hash"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
