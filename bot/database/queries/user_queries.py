"""
bot/database/queries/user_queries.py
User-related database queries for PostgreSQL
"""

import asyncpg
from typing import Optional, List
from ..models.user import User
import json
from datetime import datetime

class UserQueries:
    def __init__(self, db_pool: asyncpg.Pool):
        self.pool = db_pool
        
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by Discord ID"""
        query = """
            SELECT * FROM users WHERE id = $1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id)
            return User.from_row(dict(row)) if row else None
            
    async def get_user_by_login(self, login: str) -> Optional[User]:
        """Get user by VSB login"""
        query = """
            SELECT * FROM users WHERE login = $1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, login.lower())
            return User.from_row(dict(row)) if row else None
            
    async def upsert_user(self, user: User) -> None:
        """Insert or update user"""
        query = """
            INSERT INTO users (
                id, login, activity, type, verification, 
                real_name, attributes, verified_at, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
            ON CONFLICT (id) DO UPDATE SET
                login = EXCLUDED.login,
                activity = EXCLUDED.activity,
                type = EXCLUDED.type,
                real_name = EXCLUDED.real_name,
                attributes = EXCLUDED.attributes,
                verified_at = EXCLUDED.verified_at,
                updated_at = NOW()
        """
        attributes_json = json.dumps(user.attributes) if user.attributes else None
        
        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                user.id,
                user.login,
                user.activity,
                user.type,
                user.verification,
                user.real_name,
                attributes_json,
                user.verified_at
            )
            
    async def update_user_activity(self, user_id: str, activity: int) -> None:
        """Update user activity status"""
        query = """
            UPDATE users 
            SET activity = $1, updated_at = NOW()
            WHERE id = $2
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, activity, user_id)
            
    async def get_all_active_users(self) -> List[User]:
        """Get all active users"""
        query = """
            SELECT * FROM users WHERE activity = 1
            ORDER BY verified_at DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [User.from_row(dict(row)) for row in rows]
            
    async def get_users_by_type(self, user_type: int) -> List[User]:
        """Get users by type (0=student, 2=teacher)"""
        query = """
            SELECT * FROM users 
            WHERE type = $1 AND activity = 1
            ORDER BY login
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_type)
            return [User.from_row(dict(row)) for row in rows]


