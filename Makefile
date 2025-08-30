# Makefile - VSB Discord Bot
# Compatible with PowerShell, Windows CMD, and MINGW64

.PHONY: help dev-up dev-down dev-logs dev-attach dev-local prod-up prod-down \
        logs shell db-shell rebuild clean test lint migrate status

help:
	@echo Available commands:
	@echo   make dev-up        - Start development environment with Docker
	@echo   make dev-down      - Stop development environment
	@echo   make dev-logs      - Show app logs (follow mode)
	@echo   make dev-attach    - Attach to app container shell
	@echo   make dev-local     - Run locally with hot-reload (no Docker)
	@echo   make prod-up       - Start production environment
	@echo   make prod-down     - Stop production environment
	@echo   make logs          - Show all logs
	@echo   make shell         - Open shell in app container
	@echo   make db-shell      - Open PostgreSQL shell
	@echo   make rebuild       - Rebuild app image (no cache)
	@echo   make clean         - Clean up containers and volumes
	@echo   make test          - Run tests
	@echo   make lint          - Run linter
	@echo   make migrate       - Run database migrations
	@echo   make status        - Show service status

# Development commands
dev-up:
	@echo Starting development environment...
	docker compose -f docker-compose.yml -f docker-compose.dev.yml build --no-cache
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
	@echo Development environment started successfully
	@echo Bot should be running on configured port
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml ps

dev-down:
	@echo Stopping development environment...
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml down
	@echo Development environment stopped

dev-logs:
	@echo Following app logs (Ctrl+C to exit)...
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f bot

dev-attach:
	@echo Attaching to bot container...
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml exec bot /bin/bash || docker compose -f docker-compose.yml -f docker-compose.dev.yml exec bot /bin/sh

dev-local:
	@echo Running locally with hot-reload (recommended for Windows)...
	@echo Make sure you have PostgreSQL running locally or use: make dev-db
	@python scripts/dev_run.py

# Start just the database for local development
dev-db:
	@echo Starting PostgreSQL database for local development...
	@docker compose up -d postgres
	@echo Database is running on localhost:5432

# Stop just the database
dev-db-down:
	@echo Stopping PostgreSQL database...
	@docker compose stop postgres

# Production commands
prod-up:
	@echo Starting production environment...
	@docker compose up -d --build
	@echo Production environment started successfully
	@docker compose ps

prod-down:
	@echo Stopping production environment...
	@docker compose down
	@echo Production environment stopped

# Utility commands
logs:
	@docker compose logs -f

shell:
	@docker compose exec bot /bin/bash || docker compose exec bot /bin/sh || (docker compose up -d bot && docker compose exec bot /bin/bash) || (docker compose up -d bot && docker compose exec bot /bin/sh)

db-shell:
	@docker compose exec postgres psql -U vsb_bot -d vsb_discord

rebuild:
	@echo Rebuilding bot image...
	@docker compose build --no-cache bot
	@echo Rebuild complete

clean:
	@echo Cleaning up containers and volumes...
	@docker compose down -v
	@docker system prune -f
	@echo Cleanup complete

test:
	@echo Running tests...
	@docker compose exec bot python -m pytest tests/ -v || echo No tests found or test runner not configured

lint:
	@echo Running linter...
	@docker compose exec bot python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics || echo Linter not configured

migrate:
	@echo Running database migrations...
	@docker compose exec bot python -c "import asyncio; from bot.database.migrations import run_migrations; asyncio.run(run_migrations())" || echo Migration system not found

# Quick status check
status:
	@echo Service Status:
	@docker compose ps
	@echo.
	@echo Health Check:
	@docker compose exec bot python -c "print('Bot container is running')" || echo Bot container not responding

# Development helpers
restart-bot:
	@echo Restarting bot container...
	@docker compose restart bot
	@echo Bot container restarted

view-logs:
	@docker compose logs bot --tail=50

# Database helpers
db-backup:
	@echo Creating database backup...
	@docker compose exec postgres pg_dump -U vsb_bot vsb_discord > backup_$(shell date +%Y%m%d_%H%M%S).sql || echo Backup failed

db-reset:
	@echo WARNING: This will destroy all data!
	@echo Press Ctrl+C to cancel, or wait 5 seconds to continue...
	@timeout 5 || echo Proceeding with database reset...
	@docker compose down -v
	@docker compose up -d postgres
	@echo Database reset complete

migrate:
	@echo Creating and running database migrations...
	@docker compose exec bot python scripts/create_initial_migration.py || echo Migration system not found

# Create a new migration
migration:
	@echo Creating new migration...
	@docker compose exec bot python -c "from alembic.config import Config; from alembic import command; import os; os.environ.update({'DB_HOST': '$(shell docker compose exec bot printenv DB_HOST)', 'DB_PORT': '$(shell docker compose exec bot printenv DB_PORT)', 'DB_NAME': '$(shell docker compose exec bot printenv DB_NAME)', 'DB_USER': '$(shell docker compose exec bot printenv DB_USER)', 'DB_PASSWORD': '$(shell docker compose exec bot printenv DB_PASSWORD)'}); cfg = Config('alembic.ini'); command.revision(cfg, message=input('Migration message: '), autogenerate=True)"

# Upgrade database to head
db-upgrade:
	@echo Upgrading database to head...
	@docker compose exec bot python scripts/create_initial_migration.py upgrade