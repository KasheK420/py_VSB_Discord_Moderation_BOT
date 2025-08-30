# bot/database/models/kb.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class KBArticle:
    id: int
    title: str
    body: str
    url: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = None


@dataclass
class KBAutoReply:
    thread_id: int
    post_message_id: int
    kb_ids: List[int]


@dataclass
class KBFeedback:
    thread_id: int
    user_id: int
    helpful: bool
