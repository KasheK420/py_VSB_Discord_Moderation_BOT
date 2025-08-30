# bot/database/models/shame.py
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ShameStats:
    user_id: int
    warnings: int
    kicks: int
    bans: int
    timeouts: int
    last_event_at: datetime
