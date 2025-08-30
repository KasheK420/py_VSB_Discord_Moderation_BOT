#!/usr/bin/env python3
"""
scripts/check_database.py
Check database connection and migration status
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from bot.database.database_service import database_service
from bot.utils.config import Config
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_database():
    """Check database connection and status"""
    config = Config()
    
    print("VSB Discord Bot - Database Health Check")
    print("=" * 50)
    print(f"Host: {config.db_host}")
    print(f"Port: {config.db_port}")
    print(f"Database: {config.db_name}")
    print(f"User: {config.db_user}")
    print()
    
    try:
        # Initialize database service
        pool = await database_service.initialize()
        print("âœ… Database service initialized successfully")
        
        # Test basic connection
        async with pool.acquire() as conn:
            # Get PostgreSQL version
            version = await conn.fetchval('SELECT version()')
            print(f"âœ… PostgreSQL Version: {version.split(',')[0]}")
            
            # Get current database
            current_db = await conn.fetchval('SELECT current_database()')
            print(f"âœ… Connected to database: {current_db}")
            
            # Check if tables exist
            tables = await conn.fetch("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            
            print(f"âœ… Tables found: {len(tables)}")
            for table in tables:
                print(f"   - {table['table_name']}")
            
            # Check alembic version
            try:
                alembic_version = await conn.fetchval(
                    "SELECT version_num FROM alembic_version LIMIT 1"
                )
                print(f"âœ… Alembic version: {alembic_version}")
            except Exception:
                print("âš ï¸ No Alembic version table found (migrations not run)")
            
            # Check user count
            try:
                user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
                print(f"âœ… Users in database: {user_count}")
            except Exception as e:
                print(f"âš ï¸ Could not check users table: {e}")
            
            # Check poll count
            try:
                poll_count = await conn.fetchval("SELECT COUNT(*) FROM polls")
                print(f"âœ… Polls in database: {poll_count}")
            except Exception as e:
                print(f"âš ï¸ Could not check polls table: {e}")
        
        print("\nâœ… Database health check passed!")
        
        # Close connections
        await database_service.close()
        return True
        
    except Exception as e:
        print(f"âŒ Database health check failed: {e}")
        return False


async def main():
    """Main function"""
    success = await check_database()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))