"""
bot/database/migrations/env.py
Alembic environment configuration for PostgreSQL
"""

# Import models for autogenerate
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from bot.database.models.sqlalchemy_models import Base
from bot.utils.config import Config

# this is the Alembic Config object
config = context.config

# Load environment variables
bot_config = Config()

# Update the sqlalchemy.url with environment variables
# Use synchronous psycopg2 driver for migrations
database_url = f"postgresql://{bot_config.db_user}:{bot_config.db_password}@{bot_config.db_host}:{bot_config.db_port}/{bot_config.db_name}"
config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
