#!/usr/bin/env python3
"""
scripts/create_initial_migration.py
Create initial Alembic migration from current models
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

import asyncio

import asyncpg
from alembic import command
from alembic.config import Config as AlembicConfig

from bot.utils.config import Config


async def ensure_database_exists():
    """Ensure the database exists before running migrations"""
    config = Config()

    # Connect to postgres database to create target database
    postgres_url = f"postgresql://{config.db_user}:{config.db_password}@{config.db_host}:{config.db_port}/postgres"

    try:
        conn = await asyncpg.connect(postgres_url)

        # Check if database exists
        db_exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", config.db_name
        )

        if not db_exists:
            print(f"Creating database '{config.db_name}'...")
            await conn.execute(f'CREATE DATABASE "{config.db_name}"')
            print(f"Database '{config.db_name}' created")
        else:
            print(f"Database '{config.db_name}' already exists")

        await conn.close()

    except Exception as e:
        print(f"Error ensuring database exists: {e}")
        raise


def create_initial_migration():
    """Create the initial Alembic migration"""
    config = Config()

    # Set environment variables for alembic
    os.environ.update(
        {
            "DB_HOST": config.db_host,
            "DB_PORT": str(config.db_port),
            "DB_NAME": config.db_name,
            "DB_USER": config.db_user,
            "DB_PASSWORD": config.db_password,
        }
    )

    # Get alembic config
    alembic_ini_path = Path(__file__).parent.parent / "alembic.ini"

    if not alembic_ini_path.exists():
        print(f"Error: alembic.ini not found at {alembic_ini_path}")
        return False

    alembic_cfg = AlembicConfig(str(alembic_ini_path))

    # Create migrations directory if it doesn't exist
    script_location = alembic_cfg.get_main_option("script_location")
    migrations_dir = Path(script_location)
    migrations_dir.mkdir(parents=True, exist_ok=True)

    versions_dir = migrations_dir / "versions"
    versions_dir.mkdir(exist_ok=True)

    try:
        print("Creating initial migration...")
        command.revision(
            alembic_cfg, message="Initial migration - users and polls tables", autogenerate=True
        )
        print("Initial migration created successfully!")
        return True

    except Exception as e:
        print(f"Error creating migration: {e}")
        return False


def upgrade_database():
    """Upgrade database to head"""
    config = Config()

    # Set environment variables for alembic
    os.environ.update(
        {
            "DB_HOST": config.db_host,
            "DB_PORT": str(config.db_port),
            "DB_NAME": config.db_name,
            "DB_USER": config.db_user,
            "DB_PASSWORD": config.db_password,
        }
    )

    alembic_ini_path = Path(__file__).parent.parent / "alembic.ini"
    alembic_cfg = AlembicConfig(str(alembic_ini_path))

    try:
        print("Upgrading database to head...")
        command.upgrade(alembic_cfg, "head")
        print("Database upgraded successfully!")
        return True

    except Exception as e:
        print(f"Error upgrading database: {e}")
        return False


async def main():
    """Main function"""
    print("VSB Discord Bot - Database Migration Setup")
    print("=" * 50)

    try:
        # Ensure database exists
        await ensure_database_exists()

        # Create initial migration
        if create_initial_migration():
            print("\nNext steps:")
            print("1. Review the generated migration file")
            print("2. Run the bot - migrations will be applied automatically")
            print("3. Or manually run: python scripts/create_initial_migration.py upgrade")

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


def upgrade_only():
    """Just run the upgrade without creating migration"""
    return upgrade_database()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "upgrade":
        success = upgrade_only()
        sys.exit(0 if success else 1)
    else:
        sys.exit(asyncio.run(main()))
