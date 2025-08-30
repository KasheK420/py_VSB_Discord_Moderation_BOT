"""
bot/database/models/sqlalchemy_models.py
SQLAlchemy models for Alembic migrations
"""

from sqlalchemy import Column, String, Integer, SmallInteger, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


class User(Base):
    """User model for Discord bot authentication"""
    __tablename__ = 'users'
    
    id = Column(String(20), primary_key=True)  # Discord user ID
    login = Column(String(10), nullable=False, unique=True)  # VSB login
    activity = Column(SmallInteger, default=0)  # 0=inactive, 1=active
    type = Column(SmallInteger, nullable=False)  # 0=student, 2=teacher
    verification = Column(String(12), nullable=False)
    real_name = Column(String(150), nullable=True)
    attributes = Column(JSON, nullable=True)  # Store all OAuth2 attributes
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class Poll(Base):
    """Poll model for Discord polls"""
    __tablename__ = 'polls'
    
    id = Column(String(48), primary_key=True)  # Message ID + Channel ID
    start = Column(DateTime, nullable=False)
    end = Column(DateTime, nullable=False)
    author = Column(String(20), nullable=False)  # Discord user ID
    type = Column(SmallInteger, default=0)
    title = Column(String(255), nullable=False)
    options = Column(Text, nullable=True)
    emojis = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())


class SchemaVersion(Base):
    """Track schema versions for manual migrations"""
    __tablename__ = 'schema_version'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(Integer, nullable=False)
    applied_at = Column(DateTime, default=func.now())