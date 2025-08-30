"""
bot/database/data_migration_service.py
Data migration service for importing legacy MariaDB/MySQL data
"""

import asyncio
import asyncpg
import logging
import re
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class DataMigrationService:
    """Handles importing legacy data from MySQL/MariaDB dumps"""
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.pool = db_pool
        
    async def run_data_migration(self, dump_file_path: Path) -> bool:
        """Run data migration from dump file if needed"""
        try:
            # Check if migration already completed
            if await self._is_migration_completed():
                logger.info("Data migration already completed, skipping")
                return True
            
            if not dump_file_path.exists():
                logger.warning(f"Dump file not found: {dump_file_path}")
                return False
            
            logger.info(f"Starting data migration from {dump_file_path}")
            
            # Read and process dump file
            sql_content = self._read_dump_file(dump_file_path)
            
            if not sql_content:
                logger.error("Dump file is empty or unreadable")
                return False
            
            # Convert MySQL/MariaDB syntax to PostgreSQL
            pg_sql = self._convert_mysql_to_postgresql(sql_content)
            
            # Execute the migration
            success = await self._execute_migration(pg_sql)
            
            if success:
                # Mark migration as completed
                await self._mark_migration_completed(dump_file_path)
                logger.info("Data migration completed successfully")
            
            return success
            
        except Exception as e:
            logger.error(f"Data migration failed: {e}")
            return False
    
    async def _is_migration_completed(self) -> bool:
        """Check if data migration has already been completed"""
        try:
            async with self.pool.acquire() as conn:
                # Check if migration tracking table exists
                table_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_name = 'data_migration_log'
                    )
                """)
                
                if not table_exists:
                    return False
                
                # Check if migration was completed
                completed = await conn.fetchval("""
                    SELECT completed FROM data_migration_log 
                    WHERE migration_type = 'mariadb_import' 
                    AND completed = true
                    LIMIT 1
                """)
                
                return bool(completed)
                
        except Exception as e:
            logger.error(f"Error checking migration status: {e}")
            return False
    
    def _read_dump_file(self, dump_file_path: Path) -> Optional[str]:
        """Read dump file content"""
        try:
            with open(dump_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            logger.info(f"Read dump file: {len(content)} characters")
            return content
            
        except UnicodeDecodeError:
            # Try with latin-1 encoding if utf-8 fails
            try:
                with open(dump_file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
                logger.info(f"Read dump file with latin-1 encoding: {len(content)} characters")
                return content
            except Exception as e:
                logger.error(f"Failed to read dump file: {e}")
                return None
        except Exception as e:
            logger.error(f"Failed to read dump file: {e}")
            return None
    
    def _convert_mysql_to_postgresql(self, mysql_sql: str) -> str:
        """Convert MySQL/MariaDB SQL to PostgreSQL compatible SQL"""
        logger.info("Converting MySQL syntax to PostgreSQL...")
        
        # Start with the original content
        pg_sql = mysql_sql
        
        # Remove MySQL-specific comments and settings
        pg_sql = re.sub(r'/\*!\d+ .*? \*/;?', '', pg_sql, flags=re.DOTALL)
        pg_sql = re.sub(r'--.*?\n', '\n', pg_sql)
        
        # Remove MySQL-specific statements
        mysql_specific_patterns = [
            r'SET\s+SQL_MODE\s*=.*?;',
            r'SET\s+time_zone\s*=.*?;',
            r'SET\s+foreign_key_checks\s*=.*?;',
            r'SET\s+unique_checks\s*=.*?;',
            r'SET\s+autocommit\s*=.*?;',
            r'START\s+TRANSACTION\s*;',
            r'COMMIT\s*;',
            r'LOCK\s+TABLES.*?;',
            r'UNLOCK\s+TABLES\s*;',
        ]
        
        for pattern in mysql_specific_patterns:
            pg_sql = re.sub(pattern, '', pg_sql, flags=re.IGNORECASE)
        
        # Convert data types
        type_conversions = {
            r'\bTINYINT\b': 'SMALLINT',
            r'\bMEDIUMINT\b': 'INTEGER',
            r'\bBIGINT\(\d+\)': 'BIGINT',
            r'\bINT\(\d+\)': 'INTEGER',
            r'\bSMALLINT\(\d+\)': 'SMALLINT',
            r'\bVARCHAR\((\d+)\)': r'VARCHAR(\1)',
            r'\bTEXT\b': 'TEXT',
            r'\bMEDIUMTEXT\b': 'TEXT',
            r'\bLONGTEXT\b': 'TEXT',
            r'\bDATETIME\b': 'TIMESTAMP',
            r'\bTIMESTAMP\b': 'TIMESTAMP',
            r'\bENUM\([^)]+\)': 'VARCHAR(50)',  # Convert ENUM to VARCHAR
        }
        
        for mysql_type, pg_type in type_conversions.items():
            pg_sql = re.sub(mysql_type, pg_type, pg_sql, flags=re.IGNORECASE)
        
        # Fix AUTO_INCREMENT to SERIAL
        pg_sql = re.sub(r'(\w+)\s+INT\s+NOT\s+NULL\s+AUTO_INCREMENT', r'\1 SERIAL', pg_sql, flags=re.IGNORECASE)
        
        # Remove MySQL-specific column attributes
        pg_sql = re.sub(r'\s+AUTO_INCREMENT\s*=\s*\d+', '', pg_sql, flags=re.IGNORECASE)
        pg_sql = re.sub(r'\s+AUTO_INCREMENT', '', pg_sql, flags=re.IGNORECASE)
        pg_sql = re.sub(r'\s+COMMENT\s+[\'"][^\'\"]*[\'"]', '', pg_sql, flags=re.IGNORECASE)
        
        # Convert table options
        pg_sql = re.sub(r'\s+ENGINE\s*=\s*\w+', '', pg_sql, flags=re.IGNORECASE)
        pg_sql = re.sub(r'\s+DEFAULT\s+CHARSET\s*=\s*\w+', '', pg_sql, flags=re.IGNORECASE)
        pg_sql = re.sub(r'\s+COLLATE\s*=\s*\w+', '', pg_sql, flags=re.IGNORECASE)
        
        # Fix backticks to double quotes for identifiers
        pg_sql = re.sub(r'`([^`]+)`', r'"\1"', pg_sql)
        
        # Fix INSERT statements - remove ON DUPLICATE KEY UPDATE
        pg_sql = re.sub(r'ON\s+DUPLICATE\s+KEY\s+UPDATE.*?;', ';', pg_sql, flags=re.IGNORECASE | re.DOTALL)
        
        # Convert boolean values
        pg_sql = re.sub(r"'0'", 'FALSE', pg_sql)
        pg_sql = re.sub(r"'1'", 'TRUE', pg_sql)
        
        # Remove or convert MySQL-specific functions
        pg_sql = re.sub(r'NOW\(\)', 'CURRENT_TIMESTAMP', pg_sql, flags=re.IGNORECASE)
        
        # Clean up extra whitespace and empty lines
        pg_sql = re.sub(r'\n\s*\n', '\n', pg_sql)
        pg_sql = pg_sql.strip()
        
        logger.info("MySQL to PostgreSQL conversion completed")
        return pg_sql
    
    async def _execute_migration(self, pg_sql: str) -> bool:
        """Execute the converted SQL"""
        try:
            # Split SQL into individual statements
            statements = self._split_sql_statements(pg_sql)
            
            logger.info(f"Executing {len(statements)} SQL statements...")
            
            async with self.pool.acquire() as conn:
                # Start transaction
                async with conn.transaction():
                    executed = 0
                    skipped = 0
                    
                    for i, statement in enumerate(statements):
                        statement = statement.strip()
                        if not statement or statement == ';':
                            continue
                        
                        try:
                            # Log progress every 100 statements
                            if i % 100 == 0:
                                logger.info(f"Progress: {i}/{len(statements)} statements")
                            
                            # Handle different statement types
                            if statement.upper().startswith('CREATE TABLE'):
                                await self._execute_create_table(conn, statement)
                            elif statement.upper().startswith('INSERT'):
                                await self._execute_insert(conn, statement)
                            else:
                                await conn.execute(statement)
                            
                            executed += 1
                            
                        except Exception as e:
                            error_msg = str(e).lower()
                            
                            # Skip certain expected errors
                            if any(skip_error in error_msg for skip_error in [
                                'already exists',
                                'relation already exists',
                                'duplicate key value',
                                'violates foreign key constraint'
                            ]):
                                skipped += 1
                                continue
                            else:
                                logger.error(f"Error executing statement {i}: {e}")
                                logger.error(f"Statement: {statement[:200]}...")
                                # Continue with other statements rather than failing completely
                                skipped += 1
                                continue
                    
                    logger.info(f"Migration completed: {executed} executed, {skipped} skipped")
                    return True
                    
        except Exception as e:
            logger.error(f"Critical error during migration: {e}")
            return False
    
    def _split_sql_statements(self, sql: str) -> List[str]:
        """Split SQL content into individual statements"""
        # Simple split on semicolon (could be improved for complex cases)
        statements = []
        
        # Split by semicolon but be careful with quoted strings
        current_statement = ""
        in_string = False
        string_char = None
        
        for char in sql:
            if char in ('"', "'") and not in_string:
                in_string = True
                string_char = char
            elif char == string_char and in_string:
                in_string = False
                string_char = None
            elif char == ';' and not in_string:
                if current_statement.strip():
                    statements.append(current_statement.strip())
                current_statement = ""
                continue
            
            current_statement += char
        
        # Add final statement if exists
        if current_statement.strip():
            statements.append(current_statement.strip())
        
        return statements
    
    async def _execute_create_table(self, conn: asyncpg.Connection, statement: str):
        """Execute CREATE TABLE with IF NOT EXISTS"""
        # Add IF NOT EXISTS if not present
        if 'IF NOT EXISTS' not in statement.upper():
            statement = statement.replace('CREATE TABLE', 'CREATE TABLE IF NOT EXISTS', 1)
        
        await conn.execute(statement)
    
    async def _execute_insert(self, conn: asyncpg.Connection, statement: str):
        """Execute INSERT with conflict resolution"""
        try:
            await conn.execute(statement)
        except Exception as e:
            error_msg = str(e).lower()
            
            if 'duplicate key' in error_msg or 'already exists' in error_msg:
                # Try to convert to INSERT ON CONFLICT DO NOTHING
                if 'INSERT INTO' in statement.upper():
                    # Extract table name
                    table_match = re.search(r'INSERT\s+INTO\s+["`]?(\w+)["`]?', statement, re.IGNORECASE)
                    if table_match:
                        # Add ON CONFLICT DO NOTHING
                        statement = statement.rstrip(';') + ' ON CONFLICT DO NOTHING;'
                        await conn.execute(statement)
                        return
            
            # Re-raise if we couldn't handle it
            raise
    
    async def _mark_migration_completed(self, dump_file_path: Path):
        """Mark the migration as completed"""
        try:
            async with self.pool.acquire() as conn:
                # Create migration log table if it doesn't exist
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS data_migration_log (
                        id SERIAL PRIMARY KEY,
                        migration_type VARCHAR(50) NOT NULL,
                        source_file VARCHAR(255),
                        completed BOOLEAN DEFAULT FALSE,
                        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        notes TEXT
                    )
                """)
                
                # Insert migration record
                await conn.execute("""
                    INSERT INTO data_migration_log (
                        migration_type, source_file, completed, notes
                    ) VALUES ($1, $2, $3, $4)
                """, 
                'mariadb_import', 
                str(dump_file_path), 
                True, 
                f'Successfully imported data from {dump_file_path.name}'
                )
                
                logger.info("Migration marked as completed")
                
        except Exception as e:
            logger.error(f"Failed to mark migration as completed: {e}")
    
    async def get_migration_status(self) -> Dict:
        """Get migration status information"""
        try:
            async with self.pool.acquire() as conn:
                # Check if log table exists
                table_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_name = 'data_migration_log'
                    )
                """)
                
                if not table_exists:
                    return {"status": "not_started", "migrations": []}
                
                # Get migration records
                records = await conn.fetch("""
                    SELECT * FROM data_migration_log 
                    ORDER BY completed_at DESC
                """)
                
                migrations = []
                for record in records:
                    migrations.append({
                        "id": record['id'],
                        "type": record['migration_type'],
                        "source_file": record['source_file'],
                        "completed": record['completed'],
                        "completed_at": record['completed_at'],
                        "notes": record['notes']
                    })
                
                status = "completed" if any(m['completed'] for m in migrations) else "failed"
                
                return {
                    "status": status,
                    "migrations": migrations
                }
                
        except Exception as e:
            logger.error(f"Error getting migration status: {e}")
            return {"status": "error", "error": str(e)}