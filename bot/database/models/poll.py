"""
bot/database/models/poll.py
Poll model for PostgreSQL database
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Poll:
    id: str  # Message ID + Channel ID
    start: datetime
    end: datetime
    author: str  # Discord user ID
    type: int = 0
    title: str = ""
    options: str | None = None
    emojis: str | None = None
    created_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "start": self.start,
            "end": self.end,
            "author": self.author,
            "type": self.type,
            "title": self.title,
            "options": self.options,
            "emojis": self.emojis,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: dict) -> "Poll":
        return cls(
            id=row["id"],
            start=row["start"],
            end=row["end"],
            author=row["author"],
            type=row.get("type", 0),
            title=row.get("title", ""),
            options=row.get("options"),
            emojis=row.get("emojis"),
            created_at=row.get("created_at"),
        )
