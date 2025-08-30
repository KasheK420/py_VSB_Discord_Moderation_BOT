"""
bot/database/models/user.py
User model for PostgreSQL database
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
import json

@dataclass
class User:
    id: str  # Discord user ID
    login: str  # VSB login (e.g., 'abc0123')
    activity: int  # 0=inactive, 1=active
    type: int  # 0=student, 2=teacher
    verification: str  # Verification code
    real_name: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None  # JSON field for all OAuth attributes
    verified_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        """Convert user to dictionary"""
        return {
            'id': self.id,
            'login': self.login,
            'activity': self.activity,
            'type': self.type,
            'verification': self.verification,
            'real_name': self.real_name,
            'attributes': json.dumps(self.attributes) if self.attributes else None,
            'verified_at': self.verified_at,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
        
    @classmethod
    def from_row(cls, row: dict) -> 'User':
        """Create User from database row"""
        attributes = row.get('attributes')
        if attributes and isinstance(attributes, str):
            attributes = json.loads(attributes)
            
        return cls(
            id=row['id'],
            login=row['login'],
            activity=row['activity'],
            type=row['type'],
            verification=row['verification'],
            real_name=row.get('real_name'),
            attributes=attributes,
            verified_at=row.get('verified_at'),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

