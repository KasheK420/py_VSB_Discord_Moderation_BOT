"""
bot/services/__init__.py
Services package for VSB Discord Bot
"""

from .auth_service import AuthService
from .logging_service import EmbedLogger, LogCategory, LogLevel

__all__ = ["AuthService", "EmbedLogger", "LogLevel", "LogCategory"]
