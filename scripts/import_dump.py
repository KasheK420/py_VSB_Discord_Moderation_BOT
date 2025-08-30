#!/usr/bin/env python3
"""
scripts/import_dump.py
Import MariaDB/MySQL dump file to PostgreSQL
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from bot.database.database_service import database_service
from bot.database.data_migration_service import DataMigrationService
from bot.utils.config import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def import_dump_file(dump_path: str, force: bool = False):
    """Import dump file to PostgreSQL"""
    dump_file = Path(dump_path)
    
    print("VSB Discord Bot - Data Import Tool")
    print("=" * 50)
    print(f"Source file: {dump_file}")
    print(f"Target database: {Config().db_name}")
    print()
    
    if not dump_file.exists():
        print(f"❌ Dump file not found: {dump_file}")
        return False
    
    try:
        # Initialize database service
        pool = await database_service.initialize()
        print("✅ Database service initialized")
        
        # Create data migration service
        migration_service = DataMigrationService(pool)
        
        # Check current status
        status = await migration_service.get_migration_status()
        print(f"Migration status: {status['status']}")
        
        if status['status'] == 'completed' and not force:
            print("⚠️ Data migration already completed!")
            print("Use --force to override and re-import")
            
            # Show existing migrations
            if status['migrations']:
                print("\nExisting migrations:")
                for migration in status['migrations']:
                    print(f"  - {migration['type']}: {migration['completed_at']}")
                    if migration['notes']:
                        print(f"    Notes: {migration['notes']}")
            
            return True
        
        if force and status['status'] == 'completed':
            print("🔄 Force mode: Re-importing data...")
        
        # Run the import
        print(f"📥 Starting data import from {dump_file.name}...")
        success = await migration_service.run_data_migration(dump_file)
        
        if success:
            print("✅ Data import completed successfully!")
            
            # Show final status
            final_status = await migration_service.get_migration_status()
            if final_status['migrations']:
                latest = final_status['migrations'][0]
                print(f"Import completed at: {latest['completed_at']}")
            
        else:
            print("❌ Data import failed!")
            return False
        
        # Close database connections
        await database_service.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Import failed: {e}")
        logger.error(f"Import error: {e}", exc_info=True)
        return False


async def check_migration_status():
    """Check current migration status"""
    print("VSB Discord Bot - Migration Status")
    print("=" * 50)
    
    try:
        # Initialize database service
        pool = await database_service.initialize()
        print("✅ Database connected")
        
        # Create data migration service
        migration_service = DataMigrationService(pool)
        
        # Get status
        status = await migration_service.get_migration_status()
        
        print(f"Overall Status: {status['status'].upper()}")
        print()
        
        if status['migrations']:
            print("Migration History:")
            print("-" * 30)
            for migration in status['migrations']:
                status_icon = "✅" if migration['completed'] else "❌"
                print(f"{status_icon} {migration['type']}")
                print(f"   Source: {migration['source_file'] or 'N/A'}")
                print(f"   Date: {migration['completed_at'] or 'N/A'}")
                if migration['notes']:
                    print(f"   Notes: {migration['notes']}")
                print()
        else:
            print("No migrations found")
        
        await database_service.close()
        return True
        
    except Exception as e:
        print(f"❌ Status check failed: {e}")
        return False


def prepare_dump_file(source_path: str, target_path: str = None):
    """Prepare dump file for import"""
    source = Path(source_path)
    target = Path(target_path) if target_path else Path("data/dump.sql")
    
    print("VSB Discord Bot - Dump File Preparation")
    print("=" * 50)
    print(f"Source: {source}")
    print(f"Target: {target}")
    print()
    
    if not source.exists():
        print(f"❌ Source file not found: {source}")
        return False
    
    try:
        # Create target directory
        target.parent.mkdir(parents=True, exist_ok=True)
        
        # Read source file
        print("📖 Reading source file...")
        with open(source, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"✅ Read {len(content)} characters")
        
        # Basic cleanup for common issues
        print("🔧 Performing basic cleanup...")
        
        # Remove or replace problematic MySQL-specific content
        replacements = [
            ("ENGINE=MyISAM", "-- ENGINE=MyISAM (removed for PostgreSQL)"),
            ("ENGINE=InnoDB", "-- ENGINE=InnoDB (removed for PostgreSQL)"),
            ("AUTO_INCREMENT=", "-- AUTO_INCREMENT="),
            ("COLLATE utf8_", "-- COLLATE utf8_"),
            ("CHARACTER SET utf8", "-- CHARACTER SET utf8"),
        ]
        
        for old, new in replacements:
            content = content.replace(old, new)
        
        # Write processed file
        print("💾 Writing processed file...")
        with open(target, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Dump file prepared: {target}")
        print(f"File size: {target.stat().st_size} bytes")
        print()
        print("Next steps:")
        print("1. Review the prepared file if needed")
        print("2. Run the bot - import will happen automatically")
        print("3. Or manually run: python scripts/import_dump.py /path/to/dump.sql")
        
        return True
        
    except Exception as e:
        print(f"❌ Preparation failed: {e}")
        return False


def show_help():
    """Show help information"""
    print("VSB Discord Bot - Data Import Tool")
    print("=" * 50)
    print("Usage:")
    print("  python scripts/import_dump.py <dump_file>          - Import dump file")
    print("  python scripts/import_dump.py <dump_file> --force  - Force re-import")
    print("  python scripts/import_dump.py --status             - Check status")
    print("  python scripts/import_dump.py --prepare <file>     - Prepare dump file")
    print("  python scripts/import_dump.py --help               - Show this help")
    print()
    print("Examples:")
    print("  python scripts/import_dump.py dump.sql")
    print("  python scripts/import_dump.py /path/to/dump.sql --force")
    print("  python scripts/import_dump.py --prepare old_dump.sql")
    print("  python scripts/import_dump.py --status")


async def main():
    """Main function"""
    args = sys.argv[1:]
    
    if not args or "--help" in args:
        show_help()
        return 0
    
    if "--status" in args:
        success = await check_migration_status()
        return 0 if success else 1
    
    if "--prepare" in args:
        try:
            source_idx = args.index("--prepare") + 1
            if source_idx >= len(args):
                print("❌ Missing source file for --prepare")
                return 1
            source_file = args[source_idx]
            target_file = args[source_idx + 1] if source_idx + 1 < len(args) else None
            success = prepare_dump_file(source_file, target_file)
            return 0 if success else 1
        except Exception as e:
            print(f"❌ Prepare failed: {e}")
            return 1
    
    # Import mode
    dump_file = args[0]
    force = "--force" in args
    
    success = await import_dump_file(dump_file, force)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))