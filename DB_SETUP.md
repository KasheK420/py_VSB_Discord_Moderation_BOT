# Database Setup Guide

This bot uses PostgreSQL with automatic Alembic migrations for database management.

## Quick Start

### Development Environment

```bash
# Start the development environment
make dev-up

# The bot will automatically:
# 1. Create the database if it doesn't exist
# 2. Run all pending migrations
# 3. Start the bot

# Check database status
make shell
python scripts/check_database.py
```

### Production Environment

```bash
# Start production environment
make prod-up

# Database migrations run automatically on bot startup
```

## Manual Database Operations

### Create Initial Migration

```bash
# Create the first migration from your models
python scripts/create_initial_migration.py
```

### Create New Migration

```bash
# After changing models, create a new migration
docker compose exec bot python -c "
from alembic.config import Config
from alembic import command
import os
from bot.utils.config import Config as BotConfig

config = BotConfig()
os.environ.update({
    'DB_HOST': config.db_host,
    'DB_PORT': str(config.db_port),
    'DB_NAME': config.db_name,
    'DB_USER': config.db_user,
    'DB_PASSWORD': config.db_password,
})

alembic_cfg = Config('alembic.ini')
command.revision(alembic_cfg, message='Your migration message', autogenerate=True)
"
```

### Upgrade Database Manually

```bash
# Upgrade to latest migration
python scripts/create_initial_migration.py upgrade

# Or using make
make db-upgrade
```

## Database Models

### Adding New Models

1. Create SQLAlchemy model in `bot/database/models/sqlalchemy_models.py`:

```python
class NewModel(Base):
    __tablename__ = 'new_table'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=func.now())
```

2. Create corresponding dataclass in `bot/database/models/new_model.py`:

```python
@dataclass
class NewModel:
    id: int
    name: str
    created_at: Optional[datetime] = None
    
    @classmethod
    def from_row(cls, row: dict) -> 'NewModel':
        return cls(
            id=row['id'],
            name=row['name'],
            created_at=row.get('created_at')
        )
```

3. Create queries class in `bot/database/queries/new_model_queries.py`:

```python
class NewModelQueries:
    def __init__(self, db_pool: asyncpg.Pool):
        self.pool = db_pool
    
    async def get_by_id(self, id: int) -> Optional[NewModel]:
        query = "SELECT * FROM new_table WHERE id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, id)
            return NewModel.from_row(dict(row)) if row else None
```

4. Generate migration:

```bash
# Create migration for your changes
make migration
```

5. The migration will be automatically applied on next bot restart.

## Migration Files

Migration files are stored in `bot/database/migrations/versions/` and follow this pattern:
- `YYYY_MM_DD_HHMM-{revision}_{description}.py`

### Migration Structure

```python
def upgrade() -> None:
    """Apply changes to database"""
    op.create_table(
        'new_table',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    """Revert changes"""
    op.drop_table('new_table')
```

## Troubleshooting

### Common Issues

#### Database Connection Failed
```bash
# Check if PostgreSQL is running
docker compose ps postgres

# Check logs
docker compose logs postgres

# Restart database
docker compose restart postgres
```

#### Migration Failed
```bash
# Check current migration status
docker compose exec bot python -c "
from alembic.config import Config
from alembic import command
cfg = Config('alembic.ini')
command.current(cfg)
"

# Reset to specific revision
docker compose exec bot python -c "
from alembic.config import Config
from alembic import command
cfg = Config('alembic.ini')
command.downgrade(cfg, 'revision_id')
"
```

#### Tables Not Found
```bash
# Check database health
python scripts/check_database.py

# Manually create tables
make db-upgrade
```

### Database Health Check

```bash
# Comprehensive database check
python scripts/check_database.py
```

This will show:
- âœ… Connection status
- âœ… Tables present
- âœ… Migration status
- âœ… Row counts
- âš ï¸ Any issues found

## Environment Variables

Required for database connection:

```env
DB_HOST=postgres          # Database host
DB_PORT=5432             # Database port
DB_NAME=vsb_discord      # Database name
DB_USER=vsb_bot          # Database user
DB_PASSWORD=your_pass    # Database password
```

## Backup and Restore

### Create Backup

```bash
# Create SQL dump
docker compose exec postgres pg_dump -U vsb_bot vsb_discord > backup.sql
```

### Restore Backup

```bash
# Restore from SQL dump
docker compose exec -T postgres psql -U vsb_bot vsb_discord < backup.sql
```

## Performance Tips

1. **Connection Pooling**: The bot uses asyncpg connection pooling (10-20 connections)
2. **Indexes**: Add indexes for frequently queried columns
3. **Query Optimization**: Use EXPLAIN ANALYZE for slow queries

```python
# Example: Add index in migration
def upgrade():
    op.create_index('idx_users_login', 'users', ['login'])
```

## Development Workflow

1. Make model changes
2. Generate migration: `make migration`
3. Review generated migration file
4. Test migration: `make db-upgrade`
5. Restart bot to apply changes automatically
6. Verify with: `python scripts/check_database.py`

The bot will automatically handle database initialization and migrations on startup, making development seamless.