# bot/database/models/economy.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class XPStats:
    user_id: int
    xp: int
    points: int
    level: int
    messages: int
    reactions_received: int
    last_updated: datetime

@dataclass
class XPEvent:
    id: int
    user_id: int
    kind: str    # 'message' | 'reaction_received' | 'admin_adjust'
    delta_xp: int
    delta_points: int
    at: datetime
    meta: str | None = None
