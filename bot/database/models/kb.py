# bot/database/models/kb.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KBArticle:
    id: int
    title: str
    body: str
    url: str | None = None
    category: str | None = None
    tags: list[str] = None


@dataclass
class KBAutoReply:
    thread_id: int
    post_message_id: int
    kb_ids: list[int]


@dataclass
class KBFeedback:
    thread_id: int
    user_id: int
    helpful: bool
