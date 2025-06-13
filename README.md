# 🤖 Discord Moderation Bot

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Discord.py-2.4.0-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord.py">
  <img src="https://img.shields.io/badge/SQLite-3-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/Version-1.0.0-28a745?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/Status-Production%20Ready-brightgreen?style=for-the-badge" alt="Status">
</p>

<p align="center">
  <img src="https://img.shields.io/github/stars/YOUR_USERNAME/YOUR_REPO?style=social" alt="GitHub stars">
  <img src="https://img.shields.io/github/forks/YOUR_USERNAME/YOUR_REPO?style=social" alt="GitHub forks">
  <img src="https://img.shields.io/github/issues/YOUR_USERNAME/YOUR_REPO" alt="GitHub issues">
  <img src="https://img.shields.io/github/last-commit/YOUR_USERNAME/YOUR_REPO" alt="Last commit">
</p>

---

## 📋 Table of Contents

- [🚀 Features](#-features)
- [🏗️ Architecture](#️-architecture)
- [⚡ Quick Start](#-quick-start)
- [🔧 Installation](#-installation)
- [⚙️ Configuration](#️-configuration)
- [🛠️ Core Functions](#️-core-functions)
- [🔒 Jail System](#-jail-system)
- [📊 Services Overview](#-services-overview)
- [🚀 Deployment](#-deployment)
- [🔧 Development](#-development)
- [🛡️ Security](#️-security)
- [📚 API Reference](#-api-reference)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

---

## 🚀 Features

### 🛡️ **Advanced Moderation**
- **Intelligent Jail System** - Three-tier restriction system (timeout, hornyjail, specific channel)
- **Automated Warning System** - Persistent warning tracking with escalating punishments
- **Hall of Shame** - Automatic detection and logging of rule violations
- **Audit Logging** - Complete message edit/delete tracking
- **Anti-Spam Protection** - Message frequency and content monitoring

### 🎮 **User Engagement**
- **XP & Leveling System** - Gamified user engagement with level roles
- **Hall of Fame** - Highlight popular messages with reaction thresholds
- **Welcome System** - Dynamic welcome messages with GIF integration
- **Fun Commands** - Interactive user commands (hug, kiss, slap, etc.)
- **Text Formatting** - Rich text manipulation tools

### 🔧 **Administration Tools**
- **Slowmode Management** - Dynamic channel slowmode control
- **User Management** - Kick, ban, timeout, role management
- **Statistics Dashboard** - Server analytics and user metrics
- **Temporary Voice Channels** - Auto-creating/deleting voice rooms
- **Configuration Management** - Live configuration viewing and editing

### ⚙️ **Technical Features**
- **Modular Architecture** - Plugin-based service system
- **Database Integration** - SQLite with automated backups
- **CI/CD Pipeline** - GitHub Actions deployment automation
- **Health Monitoring** - Automatic restart and health checks
- **Production Ready** - Systemd service with security hardening

---

## 🏗️ Architecture

```mermaid
graph TB
    A[Discord API] --> B[Event Handler]
    B --> C[Service Manager]
    C --> D[Database Layer]
    C --> E[Configuration]
    C --> F[Services]
    
    F --> G[Jail Service]
    F --> H[Moderation Service]
    F --> I[Statistics Service]
    F --> J[Welcome Service]
    F --> K[XP Service]
    
    D --> L[SQLite Database]
    D --> M[Backup System]
    
    N[Web Interface] --> C
    O[Health Monitor] --> C
    P[CI/CD Pipeline] --> Q[Production Server]
```

### 🗂️ **Project Structure**

```
discord-bot/
├── 🤖 startup.py                    # Main application entry point
├── ⚙️ configuration.py              # Configuration management
├── 🗃️ database.py                   # Database abstraction layer
├── 📡 events.py                     # Discord event handlers
├── 🔧 service.py                    # Base service class
├── 📋 requirements.txt              # Python dependencies
├── 🐳 .env.template                 # Environment variables template
├── 🔄 .github/workflows/deploy.yml  # CI/CD pipeline
├── 🛡️ services/                     # Modular bot services
│   ├── 🔒 jail_service.py          # User restriction system
│   ├── ⚠️ hall_of_shame_service.py  # Violation tracking
│   ├── 📊 statistics_service.py     # Analytics and metrics
│   ├── 👋 welcome_service.py        # Member onboarding
│   ├── ⭐ hall_of_fame_service.py   # Popular content highlighting
│   ├── 🔧 user_management_*.py     # Admin and user commands
│   └── 📝 text_formatter_service.py # Text manipulation tools
├── 🛠️ utils/                        # Utility modules
│   ├── 📝 logger.py                # Logging configuration
│   └── 🎬 tenor_api_gif.py         # GIF integration
└── 📖 README.md                     # This file
```

---

## ⚡ Quick Start

### 🐍 **Prerequisites**
- Python 3.11+
- Discord Bot Token
- Server with sudo access (for production)

### 🚀 **Local Development**

```bash
# 1. Clone repository
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd discord-bot

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.template .env
nano .env  # Edit with your values

# 5. Run bot
python startup.py
```

### 🖥️ **Production Deployment**

```bash
# 1. Run automated setup script
wget https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/setup_server.sh
chmod +x setup_server.sh
sudo ./setup_server.sh https://github.com/YOUR_USERNAME/YOUR_REPO.git

# 2. Configure environment
sudo nano /opt/discord-bot/.env

# 3. Start service
sudo systemctl start discord-bot
sudo systemctl enable discord-bot
```

---

## 🔧 Installation

### 📦 **System Requirements**

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **OS** | Ubuntu 20.04+ | Ubuntu 22.04 LTS |
| **Python** | 3.11+ | 3.11+ |
| **RAM** | 512MB | 1GB+ |
| **Storage** | 5GB | 10GB+ |
| **CPU** | 1 Core | 2+ Cores |

### 🔨 **Manual Installation**

#### 1. **System Dependencies**
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y \
    python3.11 python3.11-venv python3.11-dev \
    git curl wget sqlite3 build-essential

# CentOS/RHEL
sudo yum install -y python3.11 python3.11-venv python3.11-devel \
    git curl wget sqlite gcc
```

#### 2. **Application Setup**
```bash
# Create application directory
sudo mkdir -p /opt/discord-bot
cd /opt/discord-bot

# Create dedicated user
sudo useradd -r -d /opt/discord-bot -s /bin/bash discord-bot
sudo chown -R discord-bot:discord-bot /opt/discord-bot

# Clone repository
sudo -u discord-bot git clone YOUR_REPO_URL .

# Create virtual environment
sudo -u discord-bot python3.11 -m venv venv

# Install dependencies
sudo -u discord-bot venv/bin/pip install -r requirements.txt
```

#### 3. **Service Installation**
```bash
# Copy service file
sudo cp discord-bot.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start service
sudo systemctl enable discord-bot
sudo systemctl start discord-bot
```

---

## ⚙️ Configuration

### 🔐 **Environment Variables (.env)**

The bot uses environment variables for configuration. Copy `.env.template` to `.env` and configure the following:

#### **🤖 Discord Configuration**
```bash
# Required: Your Discord bot token from Discord Developer Portal

# Required: Your Discord application/client ID

# Optional: Specific guild ID for slash command registration (faster testing)
```

#### **🔑 API Keys**
```bash
# Required: Tenor API key for GIF functionality
# Get from: https://tenor.com/developer/keyregistration
TENOR_API_KEY=ABCDEFGHIJKLMNOP

# Optional: Custom API keys for additional services
WEATHER_API_KEY=your_weather_api_key_here
GIPHY_API_KEY=your_giphy_api_key_here
```

#### **🗃️ Database Configuration**
```bash
# Database file location (default: ./data/bot_database.db)
DATABASE_PATH=/opt/discord-bot/data/bot_database.db

# Backup configuration
DATABASE_BACKUP_PATH=/opt/discord-bot/backups
DATABASE_BACKUP_INTERVAL=86400  # seconds (24 hours)
MAX_DATABASE_BACKUPS=30         # number of backups to keep

# Connection settings
DATABASE_TIMEOUT=30             # seconds
DATABASE_POOL_SIZE=10           # maximum connections
```

#### **📝 Logging Configuration**
```bash
# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# Log file location
LOG_FILE_PATH=/opt/discord-bot/logs/discord.log

# Log rotation settings
LOG_MAX_SIZE=10485760           # 10MB in bytes
LOG_BACKUP_COUNT=5              # number of log files to keep

# Optional: Discord webhook for error notifications
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/123/abc
ERROR_NOTIFICATION_THRESHOLD=5  # errors before notification
```

#### **🔧 Service Configuration**
```bash
# Service management
SERVICE_WHITELIST=jail_service,statistics_service  # comma-separated, empty for all
MAINTENANCE_MODE=false          # disable bot functionality
DEBUG_MODE=false                # enable debug logging
DEVELOPMENT_MODE=false          # enable development features

# Performance settings
MAX_CONCURRENT_OPERATIONS=100   # maximum concurrent tasks
CACHE_TTL=3600                 # cache time-to-live in seconds
RATE_LIMIT_REQUESTS=60         # requests per window
RATE_LIMIT_WINDOW=60           # rate limit window in seconds
```

#### **🌐 Web Interface (Future)**
```bash
# Web interface settings (for future GUI)
WEB_ENABLED=false              # enable web interface
WEB_PORT=8080                  # web server port
WEB_HOST=127.0.0.1            # web server host
WEB_SSL_ENABLED=false         # enable HTTPS
WEB_SSL_CERT=/path/to/cert.pem # SSL certificate path
WEB_SSL_KEY=/path/to/key.pem   # SSL private key path

# Security
SECRET_KEY=your-secret-key-here           # for session management
JWT_SECRET=your-jwt-secret-here           # for API authentication
ALLOWED_HOSTS=your-domain.com,localhost   # comma-separated allowed hosts
```

#### **🔍 Monitoring & Health**
```bash
# Health check configuration
HEALTH_CHECK_ENABLED=true      # enable health monitoring
HEALTH_CHECK_PORT=8081         # health check endpoint port
HEALTH_CHECK_INTERVAL=300      # check interval in seconds

# Metrics collection
METRICS_ENABLED=true           # enable metrics collection
PROMETHEUS_PORT=8082           # Prometheus metrics port

# Uptime monitoring
UPTIME_CHECK_URL=https://uptime-monitor.com/webhook  # external uptime service
```

#### **☁️ Backup & Cloud Integration**
```bash
# AWS S3 backup (optional)
BACKUP_S3_ENABLED=false
BACKUP_S3_BUCKET=discord-bot-backups
BACKUP_S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY

# Cloud logging (optional)
CLOUD_LOGGING_ENABLED=false
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
```

#### **🚨 Alerting & Notifications**
```bash
# Admin notifications
ADMIN_ALERT_WEBHOOK=https://discord.com/api/webhooks/admin/token
RESTART_NOTIFICATION_ENABLED=true      # notify on bot restart
ERROR_ALERT_ENABLED=true               # send error alerts
MAINTENANCE_ALERT_ENABLED=true         # notify about maintenance

# Email notifications (optional)
EMAIL_ENABLED=false
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ADMIN_EMAIL=admin@your-domain.com
```

#### **🌍 Environment & Deployment**
```bash
# Environment identification
ENVIRONMENT=production          # production, staging, development
SERVER_NAME=discord-bot-prod   # server identifier
BOT_VERSION=1.0.0              # current version
DEPLOYMENT_ID=$(date +%s)      # unique deployment identifier

# Feature flags
FEATURE_XP_SYSTEM=true         # enable XP system
FEATURE_VOICE_CHANNELS=true    # enable temporary voice channels
FEATURE_STATISTICS=true        # enable statistics tracking
FEATURE_WEB_INTERFACE=false    # enable web interface (future)
```

### 🎛️ **Configuration File (configuration.json)**

The bot also uses a JSON configuration file for Discord-specific settings:

```json
{
  "channels": {
    "meme": 690424189173235763,
    "audit-log": 1333178032327753779,
    "hornyjail": 883397179887210566
  },
  "roles": {
    "host": 690325052658548756,
    "student": 691417700949295114,
    "admin": [631140434332221462, 689908370018402343]
  },
  "services": {
    "jail_service": {
      "enabled": true,
      "max_duration_days": 30,
      "default_timeout": "1h"
    },
    "hall_of_shame": {
      "channel": 1155870576255184916,
      "bad_words": ["word1", "word2"],
      "warning_thresholds": {
        "timeout_5min": 3,
        "kick": 20,
        "ban": 30
      }
    }
  }
}
```

---

## 🛠️ Core Functions

### 🏗️ **Application Lifecycle**

#### **🚀 Startup Process (`startup.py`)**
```python
def main():
    """
    Main application entry point.
    
    Flow:
    1. Load environment variables
    2. Initialize configuration
    3. Set up database
    4. Load services dynamically
    5. Register Discord events
    6. Start bot
    """
    
    # Configuration loading
    config = Configuration.get_instance()
    
    # Service discovery and loading
    services = load_services_dynamically()
    
    # Discord client setup with proper intents
    client = discord.Client(intents=discord.Intents.all())
    
    # Event registration for all services
    register_events(client, services)
    
    # Bot authentication and startup
    client.run(os.environ.get("DISCORD_TOKEN"))
```

#### **⚙️ Configuration Management (`configuration.py`)**
```python
class Configuration:
    """
    Singleton configuration manager with hot-reload capability.
    
    Features:
    - Thread-safe singleton pattern
    - Dot notation access (e.g., "services.jail.enabled")
    - Runtime configuration updates
    - JSON schema validation
    """
    
    @staticmethod
    def get(key: str, default=None):
        """
        Get configuration value using dot notation.
        
        Args:
            key: Dot-separated path (e.g., "channels.meme")
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        
    def refresh(self):
        """Reload configuration from file."""
        
    def validate_schema(self):
        """Validate configuration against schema."""
```

#### **🗃️ Database Layer (`database.py`)**
```python
class Database:
    """
    SQLite database manager with connection pooling.
    
    Features:
    - Singleton pattern for thread safety
    - Context managers for transactions
    - Automatic schema migration
    - Connection pooling
    - Query optimization
    """
    
    @contextmanager
    def get_connection(self):
        """Get database connection with automatic commit/rollback."""
        
    def execute(self, query: str, params: tuple = ()) -> List[Row]:
        """Execute SELECT query with parameterized inputs."""
        
    def insert(self, query: str, params: tuple = ()) -> int:
        """Execute INSERT query and return last row ID."""
        
    def update(self, query: str, params: tuple = ()) -> int:
        """Execute UPDATE/DELETE query and return affected rows."""
```

### 🔒 **Jail System (`jail_service.py`)**

The jail system is the most complex service, providing three levels of user restrictions:

#### **🏛️ Core Jail Functions**

```python
class JailService(Service):
    """
    Advanced user restriction system with multiple jail types.
    
    Jail Types:
    1. TIMEOUT - Complete server restriction
    2. HORNYJAIL - Access only to specified channel
    3. SPECIFIC - Restriction from specific channels
    """
    
    async def jail_user(self, user: Member, jail_type: str, 
                       duration: str, reason: str = None,
                       target_channel: TextChannel = None):
        """
        Jail a user with specified restrictions.
        
        Args:
            user: Discord member to jail
            jail_type: "timeout", "hornyjail", or "specific"
            duration: Duration string (e.g., "1h", "30m", "2d")
            reason: Reason for jailing
            target_channel: For "specific" type only
            
        Flow:
        1. Validate jail parameters
        2. Parse duration to datetime
        3. Create database record
        4. Apply Discord restrictions
        5. Schedule automatic release
        6. Log action and notify user
        """
        
    async def _apply_jail_restrictions(self, user: Member, 
                                     jail_type: str, 
                                     target_channel_id: int = None):
        """
        Apply Discord-level restrictions based on jail type.
        
        Timeout Jail:
        - Add "Jailed" role with no permissions
        - Remove from all voice channels
        
        Hornyjail:
        - Add "Jailed" role
        - Configure role permissions:
          * Deny: All channels except hornyjail
          * Allow: Only hornyjail channel access
          
        Specific Jail:
        - Set channel-specific permission overrides
        - Deny read/send permissions for target channel
        """
        
    async def _release_user(self, user: Member, jail_id: int):
        """
        Release user from jail and restore permissions.
        
        Flow:
        1. Retrieve jail information from database
        2. Remove Discord restrictions
        3. Mark jail as inactive in database
        4. Log release action
        5. Notify user of release
        """
        
    async def _cleanup_expired_jails(self):
        """
        Background task to automatically release expired jails.
        
        Runs every 60 seconds to check for expired jails.
        Ensures users are released even if bot was offline.
        """
```

#### **🎛️ Jail Management Commands**

```python
@app_commands.command(name="jail")
async def jail_command(interaction: Interaction, 
                      user: Member, jail_type: str, 
                      duration: str, reason: str = None):
    """
    Slash command to jail users.
    
    Usage:
    /jail @user timeout 1h Spamming chat
    /jail @user hornyjail 30m Inappropriate behavior  
    /jail @user specific 2h channel:#general Being disruptive
    """

@app_commands.command(name="jaillist")
async def jail_list(interaction: Interaction):
    """View all currently jailed users with details."""

@app_commands.command(name="jailhistory") 
async def jail_history(interaction: Interaction, user: Member):
    """View complete jail history for a user."""
```

### 📊 **Statistics System (`statistics_service.py`)**

```python
class StatisticsService(Service):
    """
    Comprehensive server analytics and user metrics.
    
    Tracks:
    - Message counts (total, daily, per user)
    - Member flow (joins, leaves, net growth)
    - Voice activity (joins, time spent)
    - Command usage statistics
    - Moderation actions
    """
    
    async def track_message(self, message: Message):
        """
        Track message statistics.
        
        Updates:
        - Total server message count
        - Daily message count
        - Per-user message count
        - Channel activity metrics
        """
        
    async def generate_server_report(self) -> Embed:
        """
        Generate comprehensive server statistics report.
        
        Includes:
        - Current member count and growth
        - Message activity (total, daily averages)
        - Most active users and channels
        - Voice activity statistics
        - Moderation summary
        """
        
    async def get_user_analytics(self, user: Member) -> Dict:
        """
        Get detailed analytics for specific user.
        
        Returns:
        - Message count and daily average
        - XP and level information
        - Voice activity time
        - Warning/moderation history
        - Server join date and tenure
        """
```

### ⚠️ **Moderation System (`hall_of_shame_service.py`)**

```python
class HallOfShameService(Service):
    """
    Automated content moderation with escalating punishments.
    
    Features:
    - Real-time message scanning
    - Persistent warning system
    - Automatic punishment escalation
    - Audit logging
    """
    
    async def process_violation(self, message: Message, 
                               violations: List[str]):
        """
        Process rule violation with automatic response.
        
        Flow:
        1. Delete offending message
        2. Add warning to database
        3. Calculate punishment based on warning count
        4. Apply punishment (timeout, kick, ban)
        5. Notify user and log action
        6. Create Hall of Shame entry
        """
        
    def detect_violations(self, content: str) -> List[str]:
        """
        Detect rule violations in message content.
        
        Checks:
        - Prohibited words/phrases
        - Excessive caps
        - Spam patterns
        - Link restrictions
        - Custom filters
        """
        
    async def apply_progressive_punishment(self, user: Member, 
                                         warning_count: int):
        """
        Apply punishment based on warning count.
        
        Escalation:
        3+ warnings: 5-minute timeout
        5+ warnings: 15-minute timeout
        10+ warnings: 1-day timeout
        15+ warnings: 7-day timeout
        20+ warnings: Kick from server
        30+ warnings: Permanent ban
        """
```

### 🎮 **User Engagement (`welcome_service.py`)**

```python
class WelcomeService(Service):
    """
    New member onboarding and engagement.
    
    Features:
    - Dynamic welcome messages
    - GIF integration
    - Role assignment
    - Server introduction
    """
    
    async def welcome_member(self, member: Member):
        """
        Welcome new members with personalized message.
        
        Flow:
        1. Generate dynamic welcome text
        2. Fetch relevant GIF from Tenor API
        3. Create rich embed with server info
        4. Send to welcome channel
        5. Assign default roles
        6. Log member join
        """
        
    def generate_welcome_message(self, member: Member) -> str:
        """Generate personalized welcome message."""
        
    async def assign_default_roles(self, member: Member):
        """Assign appropriate default roles to new members."""
```

---

## 🔒 Jail System

The jail system is the flagship feature of this bot, providing sophisticated user restriction capabilities.

### 🏛️ **Jail Types**

#### **1. 🔒 Timeout Jail**
- **Purpose**: Complete server restriction
- **Implementation**: Adds "Jailed" role with no permissions
- **Effect**: User cannot see or interact with any channels
- **Use Case**: Severe violations requiring complete isolation

```bash
# Usage example
/jail @user timeout 2h Severe spamming and harassment
```

#### **2. 🔞 Hornyjail**
- **Purpose**: Restrict to designated channel only
- **Implementation**: Role permissions allow access only to hornyjail channel
- **Effect**: User can only interact in the designated hornyjail channel
- **Use Case**: Inappropriate behavior that needs redirection

```bash
# Usage example  
/jail @user hornyjail 1h Inappropriate messages in general chat
```

#### **3. 🎯 Specific Channel Jail**
- **Purpose**: Ban from specific channels
- **Implementation**: Channel-specific permission overrides
- **Effect**: User loses access to targeted channels only
- **Use Case**: Disruption in particular channels

```bash
# Usage example
/jail @user specific 30m channel:#general Disrupting ongoing discussion
```

### ⏰ **Duration System**

The jail system supports flexible duration formats:

| Format | Example | Description |
|--------|---------|-------------|
| `Xm` | `30m` | Minutes (1-1440) |
| `Xh` | `2h` | Hours (1-168) |  
| `Xd` | `7d` | Days (1-30) |

### 🗃️ **Database Schema**

```sql
-- Jails table
CREATE TABLE jails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    admin_id INTEGER NOT NULL,
    jail_type TEXT NOT NULL,
    target_channel_id INTEGER,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    reason TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Jail logs table  
CREATE TABLE jail_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jail_id INTEGER,
    action TEXT NOT NULL,
    admin_id INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details TEXT,
    FOREIGN KEY (jail_id) REFERENCES jails (id)
);
```

### 🛡️ **Security Features**

- **Permission Validation**: Ensures admin has necessary permissions
- **Duration Limits**: Prevents excessively long jails
- **Audit Trail**: Complete logging of all jail actions
- **Auto-Cleanup**: Automatic release of expired jails
- **Backup System**: Database backups prevent data loss

---

## 📊 Services Overview

### 🔧 **Core Services**

| Service | Purpose | Key Features |
|---------|---------|--------------|
| **JailService** | User restrictions | 3-tier jail system, auto-release, audit logging |
| **HallOfShameService** | Content moderation | Auto-detection, warning system, progressive punishment |
| **StatisticsService** | Analytics | Server metrics, user analytics, leaderboards |
| **WelcomeService** | Member onboarding | Dynamic messages, GIF integration, role assignment |
| **AuditService** | Message logging | Edit/delete tracking, admin notifications |

### 🎮 **Engagement Services**

| Service | Purpose | Key Features |
|---------|---------|--------------|
| **HallOfFameService** | Popular content | Reaction thresholds, auto-highlighting |
| **ReactionService** | Interactive responses | Text/GIF reactions, keyword triggers |
| **UserManagementService** | User tools | Fun commands, text formatting, self-service |
| **TemporaryVoiceService** | Voice channels | Auto-creation, cooldowns, permissions |

### 🛠️ **Utility Services**

| Service | Purpose | Key Features |
|---------|---------|--------------|
| **ConfigurationService** | Config management | Live viewing, admin commands |
| **LoggerService** | Message logging | Debug logging, activity tracking |
| **TextFormatterService** | Content creation | Rich embeds, code snippets |
| **SlowmodeService** | Chat control | Dynamic slowmode, admin triggers |

---

## 🚀 Deployment

### 🖥️ **Production Deployment**

#### **🔄 Automated Setup**
```bash
# 1. Download and run setup script
curl -O https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/setup_server.sh
chmod +x setup_server.sh
sudo ./setup_server.sh https://github.com/YOUR_USERNAME/YOUR_REPO.git

# 2. Configure environment
sudo nano /opt/discord-bot/.env

# 3. Start services
sudo systemctl start discord-bot
sudo systemctl enable discord-bot
```

#### **🐳 Docker Deployment (Alternative)**
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "startup.py"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  discord-bot:
    build: .
    restart: unless-stopped
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - DISCORD_TOKEN=${DISCORD_TOKEN}
      - TENOR_API_KEY=${TENOR_API_KEY}
```

### 🔄 **CI/CD Pipeline**

The GitHub Actions workflow automatically:

1. **🧪 Tests**: Code quality, syntax, configuration validation
2. **🚀 Deploys**: SSH to server, update code, restart service  
3. **🩺 Health Checks**: Verify service is running correctly
4. **🔄 Rollback**: Automatic rollback on failure
5. **📢 Notifications**: Discord webhook notifications

### 📊 **Monitoring**

#### **📈 Health Monitoring**
- Service status checks every 5 minutes
- Automatic restart on failure
- Resource usage monitoring (CPU, memory)
- Database health checks

#### **📝 Log Management**
- Automatic log rotation (daily, 30-day retention)
- Error log aggregation
- Performance metrics logging
- Audit trail for all admin actions

---

## 🔧 Development

### 🏠 **Local Development Setup**

```bash
# 1. Clone and setup
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd discord-bot

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install development dependencies
pip install -r requirements.txt
pip install pytest black flake8 mypy

# 4. Setup environment
cp .env.template .env
# Edit .env with your development values

# 5. Run in development mode
export DEVELOPMENT_MODE=true
python startup.py
```

### 🧪 **Testing**

```bash
# Run all tests
pytest

# Code formatting
black .

# Linting
flake8 .

# Type checking
mypy --ignore-missing-imports .
```

### 🔌 **Creating New Services**

```python
# services/my_service.py
from service import Service
import discord

def __service__():
    return MyService()

class MyService(Service):
    async def on_ready(self):
        print("MyService is ready!")
    
    async def on_message(self, message: discord.Message):
        if message.content == "!hello":
            await message.channel.send("Hello, World!")
    
    def __register_commands__(self):
        @self.commands.command(name="mycommand")
        async def my_command(interaction: discord.Interaction):
            await interaction.response.send_message("My custom command!")
```

### 🏗️ **Architecture Guidelines**

#### **🔧 Service Design Principles**
- **Single Responsibility**: Each service handles one specific function
- **Loose Coupling**: Services communicate through events and database
- **High Cohesion**: Related functionality grouped together
- **Error Isolation**: Service failures don't crash the entire bot

#### **🗃️ Database Best Practices**
- **Parameterized Queries**: Prevent SQL injection
- **Connection Pooling**: Efficient resource usage
- **Transaction Management**: Data consistency
- **Regular Backups**: Data protection

---

## 🛡️ Security

### 🔒 **Security Features**

#### **🔐 Environment Security**
- **Encrypted Secrets**: Environment variables for sensitive data
- **File Permissions**: Restricted access to configuration files  
- **User Isolation**: Dedicated system user for bot execution
- **Network Security**: Firewall configuration and fail2ban protection

#### **🛡️ Application Security**
- **Input Validation**: All user inputs sanitized and validated
- **Rate Limiting**: Command cooldowns prevent spam
- **Permission Checks**: Admin commands require proper Discord permissions
- **Audit Logging**: Complete activity logging for accountability

#### **🗃️ Database Security**
- **Prepared Statements**: Protection against SQL injection
- **Access Controls**: Database file permissions restricted
- **Backup Encryption**: Sensitive backup data protection
- **Connection Security**: Local SQLite connections only

### 🚨 **Security Monitoring**

```bash
# Monitor failed login attempts
sudo journalctl -u ssh --since "1 hour ago" | grep "Failed"

# Check bot security logs
sudo journalctl -u discord-bot | grep -i "security\|violation\|unauthorized"

# Monitor resource usage
systemctl show discord-bot --property=MemoryCurrent,CPUUsageNSec
```

---

## 📚 API Reference

### 🔧 **Configuration API**

```python
from configuration import Configuration

# Get configuration values
meme_channel = Configuration.get("channels.meme")
admin_roles = Configuration.get("roles.admin", [])

# Check service settings
jail_enabled = Configuration.get("services.jail_service.enabled", True)
```

### 🗃️ **Database API**

```python
from database import get_database

db = get_database()

# Add warning
warning_id = db.add_warning(
    user_id=123456789,
    admin_id=987654321,
    reason="Inappropriate language",
    guild_id=111111111
)

# Get user warnings
warnings = db.get_user_warnings(user_id=123456789, guild_id=111111111)

# Log moderation action
db.log_moderation_action(
    guild_id=111111111,
    user_id=123456789,
    admin_id=987654321,
    action="TIMEOUT",
    reason="Spam violation",
    duration=3600
)
```

### 🎯 **Service API**

```python
# Custom service implementation
class MyService(Service):
    async def on_message(self, message):
        """Handle incoming messages"""
        pass
    
    async def on_member_join(self, member):
        """Handle new member joins"""
        pass
    
    def __register_commands__(self):
        """Register slash commands"""
        @self.commands.command(name="example")
        async def example_command(interaction):
            await interaction.response.send_message("Example!")
```

---

## 🤝 Contributing

### 🚀 **Getting Started**

1. **🍴 Fork the repository**
2. **🌿 Create feature branch**: `git checkout -b feature/amazing-feature`
3. **💾 Commit changes**: `git commit -m 'Add amazing feature'`
4. **📤 Push branch**: `git push origin feature/amazing-feature`
5. **🔄 Open Pull Request**

### 📋 **Development Guidelines**

#### **📝 Code Style**
- Use **Black** for code formatting
- Follow **PEP 8** naming conventions
- Add **type hints** for all functions
- Write **docstrings** for classes and methods

#### **🧪 Testing Requirements**
- Add tests for new features
- Ensure all tests pass before submitting
- Test with actual Discord server (use test bot)
- Verify database migrations work correctly

#### **📚 Documentation**
- Update README.md for new features
- Add docstrings to all functions
- Include configuration examples
- Document any breaking changes

### 🐛 **Bug Reports**

When reporting bugs, please include:
- **Environment**: OS, Python version, discord.py version
- **Configuration**: Relevant configuration (redact secrets)
- **Steps to Reproduce**: Clear reproduction steps
- **Expected vs Actual**: What you expected vs what happened
- **Logs**: Relevant log entries (redact sensitive info)

### 💡 **Feature Requests**

For feature requests, please describe:
- **Use Case**: Why this feature is needed
- **Implementation**: Suggested implementation approach
- **Impact**: How it affects existing functionality
- **Alternatives**: Other solutions considered

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

### 📝 **License Summary**

✅ **Permitted**:
- Commercial use
- Modification
- Distribution
- Private use

❌ **Limitations**:
- No warranty
- No liability

📋 **Conditions**:
- Include license notice
- Include copyright notice

---

## 🙏 Acknowledgments

- **Discord.py** - Excellent Discord API wrapper
- **SQLite** - Reliable embedded database
- **GitHub Actions** - Seamless CI/CD pipeline
- **Tenor API** - GIF integration capabilities
- **Open Source Community** - Inspiration and best practices

---

## 📞 Support

### 💬 **Getting Help**

- **📖 Documentation**: Check this README and inline documentation
- **🐛 Issues**: [GitHub Issues](https://github.com/YOUR_USERNAME/YOUR_REPO/issues)
- **💡 Discussions**: [GitHub Discussions](https://github.com/YOUR_USERNAME/YOUR_REPO/discussions)
- **📧 Email**: your-email@domain.com

### 🔍 **Troubleshooting**

#### **🚫 Common Issues**

| Issue | Solution |
|-------|----------|
| **Bot not responding** | Check `sudo systemctl status discord-bot` |
| **Database errors** | Verify file permissions and disk space |
| **Permission errors** | Ensure bot has necessary Discord permissions |
| **Service won't start** | Check logs with `sudo journalctl -u discord-bot` |

#### **📊 Health Check Commands**

```bash
# Service status
sudo systemctl status discord-bot

# Recent logs
sudo journalctl -u discord-bot --since "1 hour ago"

# Resource usage
systemctl show discord-bot --property=MemoryCurrent

# Database check
ls -la /opt/discord-bot/data/

# Manual health check
/opt/discord-bot/health_check.sh
```

---

<p align="center">
  <strong>🤖 Built with ❤️ for Discord communities</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Made%20with-Python-blue?style=for-the-badge&logo=python" alt="Made with Python">
  <img src="https://img.shields.io/badge/Powered%20by-Discord.py-5865F2?style=for-the-badge&logo=discord" alt="Powered by Discord.py">
</p>