# bot/database/models/hof.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class FamePost:
    message_id: int
    channel_id: int
    author_id: int
    posted_in: int          # hall_of_fame channel id
    fame_message_id: int    # id of the post we created
    reaction_total: int
    created_at: datetime
