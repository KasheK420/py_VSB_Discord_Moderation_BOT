# bot/database/queries/__init__.py
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
from .discord_profile_queries import DiscordProfileQueries
from .discord_stats_queries import DiscordStatsQueries
from .verification_audit_queries import VerificationAuditQueries
from .cas_attributes_history_queries import CASAttributesHistoryQueries

__all__ = [
    "UserQueries",
    "PollQueries",
    "KBQueries",
    "EconomyQueries",
    "HOFQueries",
    "ShameQueries",
    "DiscordProfileQueries",
    "DiscordStatsQueries",
    "VerificationAuditQueries",
    "CASAttributesHistoryQueries",
]
