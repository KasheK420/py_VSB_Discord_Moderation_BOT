#!/usr/bin/env python3
"""
scripts/setup_with_data.py
Complete setup script with data import for new deployments
"""

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))


def run_command(cmd, check=True):
    """Run shell command and return result"""
    print(f"🔄 Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.stdout:
        print(result.stdout)
    if result.stderr and result.returncode != 0:
        print(f"❌ Error: {result.stderr}")

    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd)

    return result


async def setup_complete_environment(dump_file_path=None):
    """Complete setup including data import"""
    print("VSB Discord Bot - Complete Setup")
    print("=" * 50)
    print("This script will:")
    print("1. Setup data directory")
    print("2. Copy dump file (if provided)")
    print("3. Start the development environment")
    print("4. Verify database and import status")
    print()

    try:
        # Step 1: Setup data directory
        print("📁 Step 1: Setting up data directory...")
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        print("✅ Data directory created")

        # Step 2: Handle dump file
        if dump_file_path:
            dump_source = Path(dump_file_path)
            if dump_source.exists():
                print(f"📋 Step 2: Copying dump file from {dump_source}...")

                # Prepare the dump file
                print("🔧 Preparing dump file for PostgreSQL...")
                result = run_command(
                    f"python scripts/import_dump.py --prepare {dump_source} data/dump.sql",
                    check=False,
                )

                if result.returncode == 0:
                    print("✅ Dump file prepared and copied to data/dump.sql")
                else:
                    print("⚠️ Dump preparation had issues, copying original...")
                    shutil.copy2(dump_source, "data/dump.sql")
            else:
                print(f"❌ Dump file not found: {dump_source}")
                return False
        else:
            print("📋 Step 2: No dump file provided, skipping")

        # Step 3: Start development environment
        print("🐳 Step 3: Starting development environment...")
        print("This will:")
        print("  - Start PostgreSQL container")
        print("  - Create database")
        print("  - Run migrations")
        print("  - Import data (if dump file exists)")
        print("  - Start the bot")
        print()

        # Stop any existing containers
        run_command(
            "docker compose -f docker-compose.yml -f docker-compose.dev.yml down", check=False
        )

        # Build and start
        run_command(
            "docker compose -f docker-compose.yml -f docker-compose.dev.yml build --no-cache bot"
        )
        run_command("docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d")

        print("✅ Environment started")

        # Step 4: Wait for services to be ready
        print("⏳ Step 4: Waiting for services to start...")
        import time

        time.sleep(10)

        # Step 5: Verify setup
        print("🔍 Step 5: Verifying setup...")

        # Check if containers are running
        result = run_command(
            "docker compose -f docker-compose.yml -f docker-compose.dev.yml ps", check=False
        )

        # Check database health
        print("🏥 Checking database health...")
        result = run_command(
            "docker compose -f docker-compose.yml -f docker-compose.dev.yml exec bot python scripts/check_database.py",
            check=False,
        )

        if result.returncode == 0:
            print("✅ Database health check passed")
        else:
            print("⚠️ Database health check had issues")

        # Check import status
        print("📊 Checking import status...")
        run_command(
            "docker compose -f docker-compose.yml -f docker-compose.dev.yml exec bot python scripts/import_dump.py --status",
            check=False,
        )

        print("\n🎉 Setup completed!")
        print("=" * 50)
        print("Your VSB Discord Bot is now running with:")
        print("  🗄️  PostgreSQL database with automatic migrations")
        print("  📊 Data imported from dump file (if provided)")
        print("  🤖 Discord bot running and ready")
        print("  🔧 Development environment with hot-reload")
        print()
        print("Useful commands:")
        print("  make dev-logs     - View bot logs")
        print("  make dev-attach   - Open shell in bot container")
        print("  make db-shell     - Connect to PostgreSQL")
        print("  make import-status - Check data import status")
        print()
        print("Access your bot at: http://localhost:8080")

        return True

    except Exception as e:
        print(f"❌ Setup failed: {e}")
        print("\nTroubleshooting:")
        print("1. Check Docker is running")
        print("2. Check environment variables in .env.dev")
        print("3. Run: make dev-logs")
        return False


def show_help():
    """Show help"""
    print("VSB Discord Bot - Complete Setup")
    print("=" * 50)
    print("Usage:")
    print("  python scripts/setup_with_data.py                    - Setup without data import")
    print("  python scripts/setup_with_data.py /path/to/dump.sql  - Setup with data import")
    print("  python scripts/setup_with_data.py --help             - Show this help")
    print()
    print("This script performs a complete setup including:")
    print("  • Data directory creation")
    print("  • Dump file preparation and import")
    print("  • Database creation and migrations")
    print("  • Bot startup with all services")
    print()
    print("Examples:")
    print("  python scripts/setup_with_data.py dump.sql")
    print("  python scripts/setup_with_data.py /home/user/old_mariadb_dump.sql")


async def main():
    """Main function"""
    args = sys.argv[1:]

    if "--help" in args:
        show_help()
        return 0

    dump_file = args[0] if args else None

    if dump_file and not Path(dump_file).exists():
        print(f"❌ Dump file not found: {dump_file}")
        return 1

    success = await setup_complete_environment(dump_file)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
