# VSB Discord Moderation Bot

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Discord.py](https://img.shields.io/badge/Discord.py-2.3.0%2B-5865F2?style=flat-square&logo=discord&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?style=flat-square&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-24.0%2B-2496ED?style=flat-square&logo=docker&logoColor=white)
![Alembic](https://img.shields.io/badge/Alembic-1.13%2B-FFA116?style=flat-square)
![License](https://img.shields.io/badge/License-GPL--3.0-blue?style=flat-square)

A comprehensive Discord moderation and community management bot for the VSB Discord server, featuring AI integration, advanced moderation tools, economy system, and automated workflows.

## 📋 Features & Services (v1.0)

### Core Services
- **🔐 Authentication Service** - OAuth2 integration with secure token management
- **📊 Database Service** - PostgreSQL with Alembic migrations and connection pooling
- **📝 Logging Service** - Comprehensive embed logging with Discord integration
- **🌐 Web Server** - OAuth callback handling and health checks

### AI & Moderation
- **🤖 AI Integration** - Groq API with multiple language models (Llama, Mixtral)
- **🛡️ Smart Moderation** - Context-aware content filtering and automated actions
- **👮 Admin Commands** - Comprehensive admin tools with permission management
- **✅ Verification System** - Student/teacher verification with role assignment

### Community Features
- **👋 Welcome System** - AI-generated welcome poems and automated greetings
- **❓ Help Center** - Knowledge base with auto-reply and FAQ management
- **🏆 Hall of Fame** - Popular content tracking and highlighting
- **⚠️ Hall of Shame** - Violation tracking and public accountability
- **💰 Economy System** - XP, points, and virtual currency management
- **🎰 Gambling & Casino** - Slots, blackjack, and other games
- **🛍️ Shop System** - Virtual item purchases and role rewards

### Utility Services
- **📊 Statistics** - Server analytics and member activity tracking
- **⏰ Reminders** - Scheduled notifications with natural language processing
- **🔄 Slowmode Control** - Dynamic channel management
- **🎤 Temporary Voice** - Auto-created voice channels with permissions

## 🚨 Issues Found

### Critical
1. **Missing Primary Key** - `bot/database/migrations/env.py` imports SQLAlchemy models but some tables may lack proper primary keys
2. **Encoding Issues** - Multiple files contain mixed encoding (UTF-8 with special characters that may cause issues)
3. **Incomplete Migration** - Database migration system is partially bypassed in `database_service.py` (line 138-147)

### Warnings
1. **Hardcoded Ports** - Docker development config has hardcoded ports that may conflict
2. **Missing Error Handling** - Several async functions lack proper exception handling
3. **Deprecated Patterns** - Some Discord.py patterns may be outdated for v2.3.0+

### Minor
1. **Inconsistent Naming** - Mix of snake_case and CamelCase in service files
2. **Unused Imports** - Several files have unused imports that should be cleaned
3. **Missing Type Hints** - Many functions lack proper type annotations

## 📖 Documentation

### System Requirements
- **OS**: Ubuntu 20.04+ / Windows 10+ with WSL2
- **Python**: 3.11+
- **Docker**: 24.0+
- **PostgreSQL**: 15+
- **RAM**: 2GB minimum
- **Storage**: 10GB minimum

### Quick Start

#### Development Environment

```bash
# Clone repository
git clone https://github.com/KasheK420/py_VSB_Discord_Moderation_BOT.git
cd py_VSB_Discord_Moderation_BOT

# Copy environment template
cp .env.example .env
# Edit .env with your configuration

# Start development environment
make dev-up

# View logs
make dev-logs

# Access bot shell
make dev-attach
```

#### Production Deployment

```bash
# Build and start production
docker compose up -d --build

# Run database migrations
docker compose exec bot python scripts/create_initial_migration.py

# Check health status
curl http://localhost:80/health
```

### Configuration

#### Required Environment Variables

```env
# Discord Configuration
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_GUILD_ID=your_guild_id
DISCORD_APPLICATION_ID=your_app_id
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret
DISCORD_PUBLIC_KEY=your_public_key

# Database Configuration
DB_HOST=postgres
DB_PORT=5432
DB_NAME=vsb_discord
DB_USER=vsb_bot
DB_PASSWORD=secure_password

# API Keys
GROQ_API_KEY=your_groq_api_key
TENOR_API_KEY=your_tenor_api_key

# OAuth Configuration
OAUTH_CLIENT_ID=your_oauth_client_id
OAUTH_CLIENT_SECRET=your_oauth_client_secret
```

See `.env.example` for complete configuration options.

### Project Structure

```
py_VSB_Discord_Moderation_BOT/
├── 📁 bot/                      # Main bot application
│   ├── 📁 cogs/                # Discord command cogs
│   │   ├── admin.py           # Admin commands
│   │   ├── ai.py              # AI integration
│   │   ├── verification.py    # User verification
│   │   ├── welcome_cog.py     # Welcome system
│   │   ├── economy_cog.py     # Economy system
│   │   └── ...                # Other cogs
│   ├── 📁 database/            # Database layer
│   │   ├── 📁 migrations/     # Alembic migrations
│   │   ├── 📁 models/         # Data models
│   │   ├── 📁 queries/        # Query classes
│   │   └── database_service.py
│   ├── 📁 services/            # Core services
│   │   ├── auth_service.py
│   │   ├── logging_service.py
│   │   └── service_loader.py
│   ├── 📁 utils/              # Utilities
│   │   ├── config.py
│   │   ├── ai_helper.py
│   │   └── webserver.py
│   └── main.py                # Entry point
├── 📁 scripts/                 # Utility scripts
│   ├── dev_run.py             # Development runner
│   ├── create_initial_migration.py
│   └── check_database.py
├── 📄 docker-compose.yml       # Production config
├── 📄 docker-compose.dev.yml   # Development overrides
├── 📄 Dockerfile              # Production image
├── 📄 Dockerfile.dev          # Development image
├── 📄 requirements.txt        # Python dependencies
├── 📄 alembic.ini            # Migration config
└── 📄 Makefile               # Development commands
```

### Database Schema

The bot uses PostgreSQL with the following main tables:

- **users** - User profiles and authentication
- **polls** - Poll system data
- **kb_articles** - Knowledge base articles
- **kb_auto_replies** - Automated responses
- **kb_feedback** - User feedback tracking
- **xp_stats** - Experience and points
- **fame_posts** - Hall of Fame entries
- **shame_stats** - Violation tracking
- **shop_items** - Virtual shop inventory
- **shop_purchases** - Purchase history

### Development Commands

```bash
# Database Management
make db-shell        # PostgreSQL shell
make db-backup       # Create backup
make db-reset        # Reset database
make migrate         # Run migrations
make migration       # Create new migration

# Development
make dev-up          # Start dev environment
make dev-down        # Stop dev environment
make dev-logs        # View logs
make dev-attach      # Attach to container
make dev-local       # Run locally (no Docker)

# Production
make prod-up         # Start production
make prod-down       # Stop production
make rebuild         # Rebuild images
make clean           # Clean containers

# Testing & Quality
make test            # Run tests
make lint            # Run linter
make status          # Check status
```

### API Endpoints

- `GET /health` - Health check endpoint
- `GET /oauth/callback` - OAuth callback handler
- `GET /oauth/status` - OAuth status check

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Testing

```bash
# Run all tests
docker compose exec bot pytest tests/ -v

# Run with coverage
docker compose exec bot pytest --cov=bot --cov-report=html

# Linting
docker compose exec bot flake8 bot/
docker compose exec bot ruff check bot/
```

### Deployment

The bot supports multiple deployment methods:

#### Docker Compose (Recommended)
```bash
docker compose -f docker-compose.yml up -d
```

#### GitHub Actions CI/CD
Push to main branch triggers automatic deployment via self-hosted runner.

#### Manual Deployment
```bash
python -m bot.main
```

### Monitoring

- **Logs**: Available at `/app/logs/discord.log`
- **Database**: Health check via `scripts/check_database.py`
- **Discord**: Admin log channel for real-time monitoring

### Security

- OAuth2 authentication for web endpoints
- Environment-based configuration
- Database connection pooling with SSL
- Rate limiting on AI services
- Automated security updates via GitHub Actions

### License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

### Support

For issues, questions, or contributions:
- 📧 Email: majoros.lukas@pm.me
- 💬 Discord: [VSB Development Server](https://discord.gg/SRfBJNU)
- 🐛 Issues: [GitHub Issues](https://github.com/KasheK420/py_VSB_Discord_Moderation_BOT/issues)

### Credits

Developed by the VSB Discord Bot Team
- Lead Developer: KasheK420
- Contributors: See [CONTRIBUTORS.md](CONTRIBUTORS.md)

---

<p align="center">Made with ❤️ for the VSB Discord Community</p>