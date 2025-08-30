"""
bot/database/queries/__init__.py
Database queries package
"""
from .user_queries import UserQueries
from .poll_queries import PollQueries
from .kb_queries import KBQueries
from .economy_queries import EconomyQueries
from .hof_queries import HOFQueries
from .shame_queries import ShameQueries

__all__ = ['UserQueries','PollQueries','KBQueries','EconomyQueries','HOFQueries','ShameQueries']
