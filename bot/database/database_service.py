"""
bot/database/database_service.py
Database initialization and migration service with comprehensive logging
"""

import asyncio
import asyncpg
import logging
import subprocess
import sys
import os
from pathlib import Path
from typing import Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from alembic.config import Config as AlembicConfig
from alembic import command
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext

from ..utils.config import Config
from ..services.logging_service import LogLevel

logger = logging.getLogger(__name__)


class DatabaseService:
    """Handles database initialization, migrations, and connection management"""
    
    def __init__(self, config: Config):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None
        self.engine = None
        self.session_factory = None
        self.embed_logger = None
        self.connection_stats = {
            "connections_created": 0,
            "connections_failed": 0,
            "queries_executed": 0,
            "queries_failed": 0,
            "startup_time": None
        }
        
        # Database connection parameters
        self.db_host = config.db_host
        self.db_port = config.db_port
        self.db_name = config.db_name
        self.db_user = config.db_user
        self.db_password = config.db_password
        
        # Connection URLs
        self.sync_url = f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
        self.async_url = f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    def set_logger(self, embed_logger):
        """Set the embed logger for database operations"""
        self.embed_logger = embed_logger
        
    async def initialize(self) -> asyncpg.Pool:
        """Initialize database connection and run migrations"""
        start_time = datetime.utcnow()
        self.connection_stats["startup_time"] = start_time
        
        logger.info("Initializing database service...")
        
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Database Service",
                title="Database Initialization Started",
                description="Starting database connection and setup",
                level=LogLevel.INFO,
                fields={
                    "Host": self.db_host,
                    "Port": str(self.db_port),
                    "Database": self.db_name,
                    "User": self.db_user,
                    "Status": "🔄 Initializing..."
                }
            )
        
        try:
            # First, ensure database exists
            await self._ensure_database_exists()
            
            # Run migrations (currently skipped but logged)
            await self._run_migrations()
            
            # Create connection pool
            self.pool = await self._create_connection_pool()
            
            # Import legacy data if dump file exists (currently skipped but logged)
            # await self._run_data_import()
            
            # Create SQLAlchemy engine for migrations
            self.engine = create_async_engine(
                self.async_url,
                echo=False,
                pool_pre_ping=True
            )
            
            self.session_factory = sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Calculate initialization time
            init_time = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info(f"Database service initialized successfully in {init_time:.2f}s")
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Database Service",
                    title="Database Initialization Complete",
                    description="Database connection pool and services ready",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Initialization Time": f"{init_time:.2f}s",
                        "Connection Pool": f"Min: 10, Max: 20",
                        "Database": f"{self.db_name}@{self.db_host}:{self.db_port}",
                        "SQLAlchemy Engine": "✅ Ready",
                        "Session Factory": "✅ Ready",
                        "Status": "🟢 Operational"
                    }
                )
            
            return self.pool
            
        except Exception as e:
            init_time = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Failed to initialize database after {init_time:.2f}s: {e}")
            
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Database Service",
                    error=e,
                    context=f"Database initialization failed after {init_time:.2f}s"
                )
            raise
    
    async def _ensure_database_exists(self):
        """Ensure the target database exists"""
        logger.info(f"Checking if database '{self.db_name}' exists...")
        
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Database Service",
                title="Database Connectivity Check",
                description="Verifying database connection and availability",
                level=LogLevel.INFO,
                fields={
                    "Target Database": self.db_name,
                    "Host": self.db_host,
                    "Port": str(self.db_port),
                    "Max Attempts": "30",
                    "Status": "🔄 Connecting..."
                }
            )
        
        # Wait for PostgreSQL to be ready
        for attempt in range(30):  # Wait up to 30 seconds
            try:
                # Try to connect to the target database directly
                test_conn = await asyncpg.connect(
                    host=self.db_host,
                    port=self.db_port,
                    user=self.db_user,
                    password=self.db_password,
                    database=self.db_name
                )
                
                # Test the connection with a simple query
                version = await test_conn.fetchval('SELECT version()')
                await test_conn.close()
                
                logger.info(f"Database '{self.db_name}' is ready - PostgreSQL: {version[:50]}...")
                
                if self.embed_logger:
                    await self.embed_logger.log_custom(
                        service="Database Service",
                        title="Database Connection Successful",
                        description="Successfully connected to target database",
                        level=LogLevel.SUCCESS,
                        fields={
                            "Database": self.db_name,
                            "Attempts": str(attempt + 1),
                            "PostgreSQL Version": version[:100] + "..." if len(version) > 100 else version,
                            "Status": "✅ Connected"
                        }
                    )
                
                self.connection_stats["connections_created"] += 1
                return
                
            except Exception as e:
                self.connection_stats["connections_failed"] += 1
                if attempt < 29:
                    logger.info(f"Database not ready (attempt {attempt + 1}/30), waiting... Error: {e}")
                    await asyncio.sleep(1)
                else:
                    logger.error(f"Failed to connect to database after 30 attempts: {e}")
                    
                    if self.embed_logger:
                        await self.embed_logger.log_error(
                            service="Database Service",
                            error=e,
                            context=f"Failed to connect to database after 30 attempts ({30}s timeout)"
                        )
                    raise
    
    async def _run_migrations(self):
            """Run Alembic migrations"""
            logger.info("Checking for database migrations...")
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Database Service",
                    title="Migration Check",
                    description="Checking for database schema migrations",
                    level=LogLevel.INFO,
                    fields={
                        "Migration System": "Alembic",
                        "Status": "🔍 Checking for migrations..."
                    }
                )
            
            # TEMPORARILY BYPASS MIGRATIONS TO GET BOT WORKING
            logger.warning("TEMPORARILY SKIPPING MIGRATIONS - BYPASS MODE")
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Database Service", 
                    title="Migrations Bypassed",
                    description="Migrations temporarily disabled for debugging",
                    level=LogLevel.WARNING,
                    fields={
                        "Status": "⚠️ Bypassed - bot will start without schema checks"
                    }
                )
            return
            
            # Original migration code follows (commented out temporarily)
            """
            try:
                # Set environment variables for alembic
                os.environ.update({
                    'DB_HOST': self.db_host,
                    'DB_PORT': str(self.db_port),
                    'DB_NAME': self.db_name,
                    'DB_USER': self.db_user,
                    'DB_PASSWORD': self.db_password,
                })
                
                # Get alembic config path
                alembic_ini_path = Path(__file__).parent.parent.parent / "alembic.ini"
                
                if not alembic_ini_path.exists():
                    logger.warning("alembic.ini not found, skipping migrations")
                    if self.embed_logger:
                        await self.embed_logger.log_custom(
                            service="Database Service",
                            title="Migrations Skipped",
                            description="No alembic.ini found - skipping migration system",
                            level=LogLevel.WARNING,
                            fields={
                                "Expected Path": str(alembic_ini_path),
                                "Status": "⚠️ Skipped - no config file"
                            }
                        )
                    return
                
                # Create alembic config
                alembic_cfg = AlembicConfig(str(alembic_ini_path))
                
                # Check if migrations directory exists
                script_location = alembic_cfg.get_main_option("script_location")
                if not Path(script_location).exists():
                    logger.info("Creating migrations directory and initial migration...")
                    if self.embed_logger:
                        await self.embed_logger.log_custom(
                            service="Database Service",
                            title="Creating Migration Structure",
                            description="Initializing Alembic migration directory",
                            level=LogLevel.INFO,
                            fields={
                                "Script Location": script_location,
                                "Action": "Creating initial migration"
                            }
                        )
                    await self._create_initial_migration(alembic_cfg)
                
                # Run migrations to head
                logger.info("Applying migrations...")
                command.upgrade(alembic_cfg, "head")
                
                logger.info("Migrations completed successfully")
                if self.embed_logger:
                    await self.embed_logger.log_custom(
                        service="Database Service",
                        title="Migrations Applied",
                        description="Database schema migrations applied successfully",
                        level=LogLevel.SUCCESS,
                        fields={
                            "Migration System": "Alembic",
                            "Target": "head",
                            "Status": "✅ Up to date"
                        }
                    )
                    
            except Exception as e:
                logger.error(f"Migration failed: {e}")
                if self.embed_logger:
                    await self.embed_logger.log_error(
                        service="Database Service",
                        error=e,
                        context="Database migration process failed"
                    )
                # Don't raise here - try to continue with basic connection
                logger.warning("Continuing without migrations...")
            """
    
    async def _create_initial_migration(self, alembic_cfg: AlembicConfig):
        """Create initial migration if migrations directory doesn't exist"""
        try:
            # Initialize alembic in the migrations directory
            script_location = alembic_cfg.get_main_option("script_location")
            migrations_dir = Path(script_location)
            
            if not migrations_dir.exists():
                migrations_dir.mkdir(parents=True, exist_ok=True)
                
                # Create versions directory
                versions_dir = migrations_dir / "versions"
                versions_dir.mkdir(exist_ok=True)
                
                # Initialize script directory
                script_dir = ScriptDirectory.from_config(alembic_cfg)
                
                # Create initial migration
                logger.info("Generating initial migration...")
                command.revision(
                    alembic_cfg,
                    message="Initial migration",
                    autogenerate=True
                )
                
                if self.embed_logger:
                    await self.embed_logger.log_custom(
                        service="Database Service",
                        title="Initial Migration Created",
                        description="Generated first database migration",
                        level=LogLevel.SUCCESS,
                        fields={
                            "Migration Directory": str(migrations_dir),
                            "Type": "Autogenerated",
                            "Message": "Initial migration"
                        }
                    )
                
        except Exception as e:
            logger.error(f"Failed to create initial migration: {e}")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Database Service",
                    error=e,
                    context="Failed to create initial Alembic migration"
                )
            raise
    
    async def _create_connection_pool(self) -> asyncpg.Pool:
        """Create asyncpg connection pool"""
        logger.info(f"Creating connection pool to {self.db_host}:{self.db_port}/{self.db_name}")
        
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Database Service",
                title="Connection Pool Creation",
                description="Creating asyncpg connection pool",
                level=LogLevel.INFO,
                fields={
                    "Host": self.db_host,
                    "Port": str(self.db_port),
                    "Database": self.db_name,
                    "Min Connections": "10",
                    "Max Connections": "20",
                    "Command Timeout": "60s"
                }
            )
        
        try:
            pool = await asyncpg.create_pool(
                host=self.db_host,
                port=self.db_port,
                user=self.db_user,
                password=self.db_password,
                database=self.db_name,
                min_size=10,
                max_size=20,
                command_timeout=60
            )
            
            # Test connection
            async with pool.acquire() as conn:
                version = await conn.fetchval('SELECT version()')
                current_db = await conn.fetchval('SELECT current_database()')
                connection_count = await conn.fetchval('SELECT count(*) FROM pg_stat_activity WHERE datname = $1', self.db_name)
                
                logger.info(f"Connected to PostgreSQL: {version[:50]}...")
                logger.info(f"Connected to database: {current_db}")
                logger.info(f"Active connections to database: {connection_count}")
                
                if current_db != self.db_name:
                    error = Exception(f"Connected to wrong database: {current_db}, expected: {self.db_name}")
                    if self.embed_logger:
                        await self.embed_logger.log_error(
                            service="Database Service",
                            error=error,
                            context="Database name mismatch after connection"
                        )
                    raise error
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Database Service",
                    title="Connection Pool Ready",
                    description="Database connection pool created successfully",
                    level=LogLevel.SUCCESS,
                    fields={
                        "PostgreSQL": version[:100] + "..." if len(version) > 100 else version,
                        "Database": current_db,
                        "Pool Size": "10-20 connections",
                        "Active Connections": str(connection_count),
                        "Status": "✅ Pool ready"
                    }
                )
            
            self.connection_stats["connections_created"] += 1
            return pool
            
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Database Service",
                    error=e,
                    context=f"Failed to create connection pool to {self.db_host}:{self.db_port}/{self.db_name}"
                )
            self.connection_stats["connections_failed"] += 1
            raise
    
    async def close(self):
        """Close all database connections"""
        logger.info("Closing database connections...")
        
        if self.embed_logger:
            uptime = None
            if self.connection_stats["startup_time"]:
                uptime = (datetime.utcnow() - self.connection_stats["startup_time"]).total_seconds()
            
            await self.embed_logger.log_custom(
                service="Database Service",
                title="Database Shutdown",
                description="Closing all database connections",
                level=LogLevel.WARNING,
                fields={
                    "Connection Pool": "Closing...",
                    "SQLAlchemy Engine": "Disposing...",
                    "Uptime": f"{uptime:.2f}s" if uptime else "Unknown",
                    "Connections Created": str(self.connection_stats["connections_created"]),
                    "Connection Failures": str(self.connection_stats["connections_failed"]),
                    "Status": "🔴 Shutting down"
                }
            )
        
        errors = []
        
        if self.pool:
            try:
                await self.pool.close()
                logger.info("Connection pool closed")
            except Exception as e:
                errors.append(f"Pool close error: {e}")
                logger.error(f"Error closing connection pool: {e}")
            
        if self.engine:
            try:
                await self.engine.dispose()
                logger.info("SQLAlchemy engine disposed")
            except Exception as e:
                errors.append(f"Engine dispose error: {e}")
                logger.error(f"Error disposing SQLAlchemy engine: {e}")
        
        if self.embed_logger:
            if errors:
                await self.embed_logger.log_custom(
                    service="Database Service",
                    title="Database Shutdown with Errors",
                    description="Database shutdown completed with some errors",
                    level=LogLevel.ERROR,
                    fields={
                        "Errors": "\n".join(errors),
                        "Status": "🔴 Shutdown with issues"
                    }
                )
            else:
                await self.embed_logger.log_custom(
                    service="Database Service",
                    title="Database Shutdown Complete",
                    description="All database connections closed successfully",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Status": "🔴 Clean shutdown"
                    }
                )
        
        logger.info("Database service shutdown complete")
    
    async def health_check(self) -> bool:
        """Check database connection health"""
        try:
            if not self.pool:
                return False
                
            async with self.pool.acquire() as conn:
                await conn.fetchval('SELECT 1')
                self.connection_stats["queries_executed"] += 1
                return True
                
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            self.connection_stats["queries_failed"] += 1
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Database Service",
                    error=e,
                    context="Database health check failed"
                )
            return False
    
    async def execute_query(self, query: str, *args, fetch_type: str = "val"):
        """Execute a query with logging"""
        if not self.pool:
            raise RuntimeError("Database not initialized")
        
        try:
            async with self.pool.acquire() as conn:
                if fetch_type == "val":
                    result = await conn.fetchval(query, *args)
                elif fetch_type == "row":
                    result = await conn.fetchrow(query, *args)
                elif fetch_type == "all":
                    result = await conn.fetch(query, *args)
                else:
                    result = await conn.execute(query, *args)
                
                self.connection_stats["queries_executed"] += 1
                return result
                
        except Exception as e:
            self.connection_stats["queries_failed"] += 1
            logger.error(f"Query execution failed: {e}")
            
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Database Service",
                    error=e,
                    context=f"Query execution failed - Query: {query[:100]}..."
                )
            raise
    
    def get_session(self) -> AsyncSession:
        """Get SQLAlchemy session"""
        if not self.session_factory:
            raise RuntimeError("Database not initialized")
        return self.session_factory()
    
    async def get_stats(self) -> dict:
        """Get database service statistics"""
        stats = dict(self.connection_stats)
        
        if stats["startup_time"]:
            stats["uptime_seconds"] = (datetime.utcnow() - stats["startup_time"]).total_seconds()
            stats["startup_time"] = stats["startup_time"].isoformat()
        
        # Add pool statistics if available
        if self.pool:
            stats.update({
                "pool_size": self.pool.get_size(),
                "pool_max_size": self.pool.get_max_size(),
                "pool_min_size": self.pool.get_min_size(),
            })
        
        # Add database info
        try:
            if self.pool:
                async with self.pool.acquire() as conn:
                    db_size = await conn.fetchval(
                        "SELECT pg_size_pretty(pg_database_size($1))", 
                        self.db_name
                    )
                    active_connections = await conn.fetchval(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname = $1", 
                        self.db_name
                    )
                    stats.update({
                        "database_size": db_size,
                        "active_connections": active_connections
                    })
        except Exception as e:
            stats["stats_error"] = str(e)
        
        return stats


# Global database service instance
database_service = DatabaseService(Config())

def get_database_service():
    """
    DEPRECATED: Prefer importing `database_service` directly.
    Exists to support legacy code that does:
        from bot.database.database_service import get_database_service
    """
    return database_service

def get_pool():
    """
    Convenience accessor used by some older modules.
    Prefer: `from bot.database.database_service import database_service`
            and then `database_service.pool`
    """
    return database_service.pool

# Optional, but helps static analyzers / star-imports
__all__ = [
    "DatabaseService",
    "database_service",
    "get_database_service",
    "get_pool",
]