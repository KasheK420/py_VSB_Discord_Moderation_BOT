# bot/database/models/cas_attributes_history.py
"""
CASAttributesHistory model (matches table: cas_attributes_history)
"""
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class CASAttributesHistory:
    id: int | None
    discord_id: int
    login: str
    attributes: dict[str, Any]
    received_at: datetime | None = None

    def to_row_values(self) -> tuple:
        # for inserts
        return (self.discord_id, self.login, json.dumps(self.attributes))

    @classmethod
    def from_row(cls, row: dict) -> "CASAttributesHistory":
        attrs = row.get("attributes")
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except Exception:
                attrs = {}
        return cls(
            id=row.get("id"),
            discord_id=int(row["discord_id"]),
            login=row["login"],
            attributes=attrs if isinstance(attrs, dict) else {},
            received_at=row.get("received_at"),
        )
