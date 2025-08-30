#!/usr/bin/env python3
"""
Test database connection to verify environment variables are correct.
Place this in scripts/ folder and run it in the bot container.
"""

import asyncio
import os
import sys

import asyncpg


async def test_connection():
    """Test database connection with current environment variables"""

    # Print current environment variables
    print("=" * 50)
    print("ENVIRONMENT VARIABLES:")
    print("=" * 50)
    print(f"DB_HOST: {os.getenv('DB_HOST', 'NOT SET')}")
    print(f"DB_PORT: {os.getenv('DB_PORT', 'NOT SET')}")
    print(f"DB_NAME: {os.getenv('DB_NAME', 'NOT SET')}")
    print(f"DB_USER: {os.getenv('DB_USER', 'NOT SET')}")
    print(
        f"DB_PASSWORD: {'*' * len(os.getenv('DB_PASSWORD', '')) if os.getenv('DB_PASSWORD') else 'NOT SET'}"
    )
    print()

    # Construct connection parameters
    db_host = os.getenv("DB_HOST", "postgres")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_name = os.getenv("DB_NAME", "vsb_discord")
    db_user = os.getenv("DB_USER", "vsb_bot")
    db_password = os.getenv("DB_PASSWORD", "")

    print("=" * 50)
    print("CONNECTION PARAMETERS:")
    print("=" * 50)
    print(f"Host: {db_host}")
    print(f"Port: {db_port}")
    print(f"Database: {db_name}")  # This should be 'vsb_discord'!
    print(f"User: {db_user}")
    print()

    # Try to connect
    print("=" * 50)
    print("ATTEMPTING CONNECTION:")
    print("=" * 50)

    try:
        # Test with a single connection first
        print(f"Connecting to postgresql://{db_user}@{db_host}:{db_port}/{db_name}")

        conn = await asyncpg.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name,  # This is the critical parameter!
        )

        # If we got here, connection succeeded
        print("✓ Connection successful!")

        # Run a test query
        version = await conn.fetchval("SELECT version()")
        print(f"✓ PostgreSQL version: {version[:50]}...")

        current_db = await conn.fetchval("SELECT current_database()")
        print(f"✓ Connected to database: {current_db}")

        current_user = await conn.fetchval("SELECT current_user")
        print(f"✓ Connected as user: {current_user}")

        # List all databases
        databases = await conn.fetch("SELECT datname FROM pg_database WHERE datistemplate = false")
        print(f"✓ Available databases: {[db['datname'] for db in databases]}")

        await conn.close()

        # Now test creating a pool (as the bot does)
        print()
        print("Testing connection pool creation (as bot does)...")
        pool = await asyncpg.create_pool(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name,
            min_size=1,
            max_size=2,
        )
        print("✓ Connection pool created successfully!")
        await pool.close()

        print()
        print("=" * 50)
        print("SUCCESS: All database connections working!")
        print("=" * 50)
        return True

    except asyncpg.exceptions.InvalidCatalogNameError as e:
        print(f"✗ ERROR: Database does not exist: {e}")
        print(f"  The connection is trying to use database: '{db_name}'")
        print(
            f"  But it seems to be looking for: '{str(e).split('does not exist')[0].split('database ')[-1].strip('\"')}'"
        )
        print()
        print("DIAGNOSIS: Check that DB_NAME environment variable is set correctly!")
        return False

    except Exception as e:
        print(f"✗ ERROR: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)
