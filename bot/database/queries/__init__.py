"""
bot/database/queries/__init__.py
Database queries package
"""

from .economy_queries import EconomyQueries
from .hof_queries import HOFQueries
from .kb_queries import KBQueries
from .poll_queries import PollQueries
from .shame_queries import ShameQueries
from .user_queries import UserQueries

__all__ = [
    "UserQueries",
    "PollQueries",
    "KBQueries",
    "EconomyQueries",
    "HOFQueries",
    "ShameQueries",
]
