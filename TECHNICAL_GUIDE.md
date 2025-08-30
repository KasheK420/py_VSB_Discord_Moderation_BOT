# Technical Architecture Guide

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Core Components](#core-components)
3. [Database Architecture](#database-architecture)
4. [Service Layer](#service-layer)
5. [Discord Integration](#discord-integration)
6. [AI Integration](#ai-integration)
7. [Asynchronous Patterns](#asynchronous-patterns)
8. [Security Implementation](#security-implementation)
9. [Performance Optimization](#performance-optimization)
10. [Deployment Architecture](#deployment-architecture)
11. [Monitoring & Observability](#monitoring--observability)
12. [Troubleshooting Guide](#troubleshooting-guide)

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Discord API                          │
└────────────────┬────────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────────┐
│                    Discord.py Gateway                        │
│                  (WebSocket Connection)                      │
└────────────────┬────────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────────┐
│                      VSB Bot Core                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │   Main   │  │   Cogs   │  │ Services │  │   Utils  │   │
│  │  Loop    │  │  System  │  │  Layer   │  │  Layer   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└────────────────┬────────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────────┐
│                    Data Layer                                │
│  ┌──────────────────┐  ┌──────────────┐  ┌─────────────┐   │
│  │   PostgreSQL     │  │    Redis     │  │   File      │   │
│  │   (Primary DB)   │  │   (Cache)    │  │   System    │   │
│  └──────────────────┘  └──────────────┘  └─────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### Component Interaction Flow

```python
# Simplified request flow
User Message → Discord API → Gateway → Event Handler → Cog → Service → Database
                                            ↓
                                        Response
                                            ↓
                              Discord API ← Gateway ← Command Response
```

## Core Components

### 1. Bot Initialization (`bot/main.py`)

```python
class VSBBot(commands.Bot):
    """
    Main bot class extending discord.py Bot.
    
    Initialization sequence:
    1. Configure intents and command prefix
    2. Initialize database connection pool
    3. Setup logging service
    4. Load core services
    5. Register cogs
    6. Sync slash commands
    """
    
    async def setup_hook(self):
        """
        Called during bot startup.
        Order matters - dependencies must be initialized first.
        """
        # 1. Database MUST be first (other services depend on it)
        await self.db_service.initialize()
        
        # 2. Core services (auth, logging, web)
        await init_core_services(self, self.config)
        
        # 3. AI and moderation services
        await init_ai_and_moderation(self)
        
        # 4. Load cogs (commands and event handlers)
        await self._load_cogs()
        
        # 5. Sync slash commands to Discord
        await self._sync_commands()
```

### 2. Service Loader Pattern (`bot/services/service_loader.py`)

```python
async def init_core_services(bot, config):
    """
    Initialize services in dependency order.
    
    Returns:
        tuple: (embed_logger, auth_service, web_server)
    """
    # Database is already initialized
    
    # Auth service for OAuth
    auth = AuthService(config)
    bot.auth_service = auth
    
    # Web server for OAuth callbacks
    web = OAuthWebServer(bot, config)
    await web.start()
    bot.web_server = web
    
    # Embed logger (requires guild cache)
    # This is deferred until on_ready if guild not cached
    embed_logger = None
    if config.admin_log_channel_id:
        try:
            embed_logger = EmbedLogger(bot, config.admin_log_channel_id)
            await embed_logger.setup()
        except Exception:
            pass  # Will retry in on_ready
    
    return embed_logger, auth, web
```

### 3. Configuration Management (`bot/utils/config.py`)

```python
@dataclass
class Config:
    """
    Centralized configuration using environment variables.
    
    Features:
    - Type conversion
    - Default values
    - Validation
    - Environment-based overrides
    """
    
    # Discord Configuration
    bot_token: str = field(default_factory=lambda: os.getenv("DISCORD_BOT_TOKEN", ""))
    guild_id: int = field(default_factory=lambda: int(os.getenv("DISCORD_GUILD_ID", "0")))
    
    # Database Configuration
    db_host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    db_port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.bot_token:
            raise ValueError("DISCORD_BOT_TOKEN is required")
        if not self.db_password:
            raise ValueError("DB_PASSWORD is required")
```

## Database Architecture

### Connection Pool Management

```python
class DatabaseService:
    """
    Manages PostgreSQL connections using asyncpg pool.
    
    Pool configuration:
    - min_size: 10 (minimum idle connections)
    - max_size: 20 (maximum total connections)
    - max_queries: 50000 (queries before connection reset)
    - max_inactive_connection_lifetime: 300 (seconds)
    """
    
    async def initialize(self):
        self.pool = await asyncpg.create_pool(
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            user=self.db_user,
            password=self.db_password,
            min_size=10,
            max_size=20,
            max_queries=50000,
            max_inactive_connection_lifetime=300,
            command_timeout=60
        )
```

### Migration System (Alembic)

```python
# Migration workflow
"""
1. Models defined in bot/database/models/sqlalchemy_models.py
2. Alembic generates migrations from model changes
3. Migrations applied automatically on startup
4. Rollback capability for failed deployments
"""

# Creating migrations
alembic revision --autogenerate -m "Add new table"

# Migration file structure
def upgrade():
    op.create_table(
        'example_table',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'))
    )
    op.create_index('idx_example_created', 'example_table', ['created_at'])

def downgrade():
    op.drop_index('idx_example_created')
    op.drop_table('example_table')
```

### Query Patterns

```python
class UserQueries:
    """
    Database query patterns using asyncpg.
    
    Patterns:
    - Connection acquisition from pool
    - Prepared statements for performance
    - Transaction management
    - Error handling and retry logic
    """
    
    async def get_user(self, user_id: int) -> Optional[User]:
        query = """
            SELECT id, login, role, verified, 
                   created_at, updated_at
            FROM users 
            WHERE id = $1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id)
            return User.from_row(dict(row)) if row else None
    
    async def bulk_insert_users(self, users: List[User]):
        """Efficient bulk insert using COPY."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.copy_records_to_table(
                    'users',
                    records=[(u.id, u.login, u.role) for u in users],
                    columns=['id', 'login', 'role']
                )
```

### Database Schema Design

```sql
-- Core tables with proper indexing
CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    login VARCHAR(50) UNIQUE NOT NULL,
    role VARCHAR(20) NOT NULL,
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_verified ON users(verified) WHERE verified = true;

-- Junction tables for many-to-many relationships
CREATE TABLE user_roles (
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    role_id BIGINT REFERENCES roles(id) ON DELETE CASCADE,
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    granted_by BIGINT REFERENCES users(id),
    PRIMARY KEY (user_id, role_id)
);

-- Audit tables for tracking changes
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,
    operation VARCHAR(10) NOT NULL,
    user_id BIGINT,
    changed_data JSONB,
    occurred_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Service Layer

### Service Base Class Pattern

```python
class BaseService:
    """
    Abstract base for all services.
    
    Lifecycle methods:
    - initialize(): Setup service resources
    - start(): Begin service operation
    - stop(): Graceful shutdown
    - health_check(): Service health status
    """
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db_service
        self._running = False
        self._tasks = []
    
    async def initialize(self):
        """Initialize service resources."""
        pass
    
    async def start(self):
        """Start service operations."""
        self._running = True
        self._tasks.append(asyncio.create_task(self._run()))
    
    async def stop(self):
        """Stop service gracefully."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
```

### Dependency Injection

```python
# Service dependencies are injected through constructor
class ModerationService(BaseService):
    def __init__(self, bot: commands.Bot, ai_service: AIService):
        super().__init__(bot)
        self.ai = ai_service  # Injected dependency
```

## Discord Integration

### Event Handling Architecture

```python
class EventHandler:
    """
    Centralized event handling with priority system.
    
    Event flow:
    1. Discord.py receives event
    2. Event dispatcher checks handlers
    3. Handlers execute in priority order
    4. Errors are caught and logged
    """
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Skip bot messages
        if message.author.bot:
            return
        
        # Process through handler chain
        for handler in self.message_handlers:
            try:
                if await handler.should_handle(message):
                    await handler.handle(message)
                    if handler.stops_chain:
                        break
            except Exception as e:
                await self.handle_error(e, message)
```

### Slash Command Implementation

```python
@app_commands.command(name="moderate", description="Moderate content")
@app_commands.describe(
    action="Action to take",
    target="Target user or message",
    reason="Reason for moderation"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Warn", value="warn"),
    app_commands.Choice(name="Mute", value="mute"),
    app_commands.Choice(name="Ban", value="ban")
])
async def moderate_command(
    self,
    interaction: discord.Interaction,
    action: str,
    target: discord.Member,
    reason: str
):
    """
    Slash command with:
    - Parameter validation
    - Permission checking
    - Audit logging
    - Error handling
    """
    # Defer for long operations
    await interaction.response.defer(ephemeral=True)
    
    # Permission check
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.followup.send("Insufficient permissions")
        return
    
    # Execute moderation
    result = await self.moderation_service.execute(action, target, reason)
    
    # Respond
    await interaction.followup.send(embed=result.to_embed())
```

### Context Menu Commands

```python
# Right-click context menu for messages
self.ctx_menu = app_commands.ContextMenu(
    name="Analyze Message",
    callback=self.analyze_message
)

async def analyze_message(
    self, 
    interaction: discord.Interaction, 
    message: discord.Message
):
    """Context menu handler with AI analysis."""
    analysis = await self.ai_service.analyze(message.content)
    await interaction.response.send_message(
        embed=analysis.to_embed(),
        ephemeral=True
    )
```

## AI Integration

### Groq API Integration

```python
class AIService:
    """
    AI service using Groq API with multiple models.
    
    Features:
    - Model selection based on task
    - Token counting and limiting
    - Response streaming
    - Caching layer
    - Rate limiting
    """
    
    MODELS = {
        "fast": "llama-3.2-1b-preview",
        "balanced": "llama-3.2-3b-preview", 
        "quality": "llama-3.1-70b-versatile",
        "huge": "llama-3.3-70b-versatile"
    }
    
    async def complete(
        self,
        prompt: str,
        model: str = "balanced",
        max_tokens: int = 1000,
        temperature: float = 0.7
    ):
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        payload = {
            "model": self.MODELS[model],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/v1/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                data = await response.json()
                return data["choices"][0]["message"]["content"]
```

### Smart Moderation System

```python
class SmartModerationService:
    """
    AI-powered content moderation.
    
    Pipeline:
    1. Content preprocessing
    2. AI classification
    3. Confidence scoring
    4. Action determination
    5. Audit logging
    """
    
    async def analyze_content(self, content: str) -> ModerationResult:
        # Preprocess
        cleaned = self.preprocess(content)
        
        # AI Classification
        classification = await self.ai.classify(
            cleaned,
            categories=["toxic", "spam", "nsfw", "hate"]
        )
        
        # Determine action based on confidence
        if classification.max_confidence > 0.95:
            action = "auto_delete"
        elif classification.max_confidence > 0.80:
            action = "flag_for_review"
        else:
            action = "allow"
        
        return ModerationResult(
            content=content,
            classification=classification,
            action=action,
            confidence=classification.max_confidence
        )
```

## Asynchronous Patterns

### Task Management

```python
class TaskManager:
    """
    Manages long-running async tasks.
    
    Features:
    - Task lifecycle management
    - Error recovery
    - Graceful shutdown
    - Task monitoring
    """
    
    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = False
    
    async def start_task(
        self,
        name: str,
        coro: Coroutine,
        restart_on_error: bool = True
    ):
        """Start managed task with error recovery."""
        async def wrapper():
            while self._running:
                try:
                    await coro
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Task {name} failed: {e}")
                    if restart_on_error:
                        await asyncio.sleep(5)
                        continue
                    break
        
        self._tasks[name] = asyncio.create_task(wrapper())
    
    async def shutdown(self):
        """Gracefully shutdown all tasks."""
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
```

### Concurrent Operations

```python
async def process_batch(items: List[Any], processor: Callable):
    """
    Process items concurrently with rate limiting.
    
    Uses semaphore to limit concurrent operations.
    """
    semaphore = asyncio.Semaphore(10)  # Max 10 concurrent
    
    async def process_with_limit(item):
        async with semaphore:
            return await processor(item)
    
    results = await asyncio.gather(
        *[process_with_limit(item) for item in items],
        return_exceptions=True
    )
    
    # Handle results and exceptions
    successful = [r for r in results if not isinstance(r, Exception)]
    failed = [r for r in results if isinstance(r, Exception)]
    
    return successful, failed
```

### Event Emitter Pattern

```python
class EventEmitter:
    """
    Custom event system for internal communication.
    """
    
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
    
    def on(self, event: str, handler: Callable):
        """Register event handler."""
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)
    
    async def emit(self, event: str, *args, **kwargs):
        """Emit event to all handlers."""
        if event in self._handlers:
            tasks = [
                asyncio.create_task(handler(*args, **kwargs))
                for handler in self._handlers[event]
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
```

## Security Implementation

### Authentication & Authorization

```python
class AuthService:
    """
    Handles authentication and authorization.
    
    Features:
    - OAuth2 flow
    - JWT token management
    - Role-based access control
    - Session management
    """
    
    def create_token(self, user_id: int, scopes: List[str]) -> str:
        """Create JWT token with expiration."""
        payload = {
            "user_id": user_id,
            "scopes": scopes,
            "exp": datetime.utcnow() + timedelta(hours=24),
            "iat": datetime.utcnow()
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")
    
    async def verify_token(self, token: str) -> Optional[Dict]:
        """Verify and decode JWT token."""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"]
            )
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
```

### Input Validation

```python
class InputValidator:
    """
    Input validation and sanitization.
    """
    
    @staticmethod
    def sanitize_sql(value: str) -> str:
        """Prevent SQL injection."""
        # Use parameterized queries instead
        # This is just for extra safety
        dangerous_chars = ["'", '"', ';', '--', '/*', '*/']
        for char in dangerous_chars:
            value = value.replace(char, '')
        return value
    
    @staticmethod
    def validate_discord_id(value: str) -> bool:
        """Validate Discord snowflake ID."""
        try:
            id_int = int(value)
            return 0 < id_int < 2**63
        except ValueError:
            return False
```

### Rate Limiting

```python
class RateLimiter:
    """
    Token bucket rate limiter.
    """
    
    def __init__(self, rate: int, per: float):
        self.rate = rate
        self.per = per
        self.allowance = rate
        self.last_check = time.monotonic()
    
    async def check(self, key: str) -> bool:
        """Check if request is allowed."""
        current = time.monotonic()
        time_passed = current - self.last_check
        self.last_check = current
        
        self.allowance += time_passed * (self.rate / self.per)
        if self.allowance > self.rate:
            self.allowance = self.rate
        
        if self.allowance < 1.0:
            return False
        
        self.allowance -= 1.0
        return True
```

## Performance Optimization

### Caching Strategy

```python
class CacheService:
    """
    Multi-tier caching system.
    
    Tiers:
    1. Memory (LRU cache)
    2. Redis (distributed cache)
    3. Database (persistent storage)
    """
    
    def __init__(self, redis_url: str):
        self.memory_cache = LRUCache(maxsize=1000)
        self.redis = aioredis.from_url(redis_url)
    
    async def get(self, key: str) -> Optional[Any]:
        # Check memory cache
        if key in self.memory_cache:
            return self.memory_cache[key]
        
        # Check Redis
        value = await self.redis.get(key)
        if value:
            self.memory_cache[key] = value
            return value
        
        return None
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 3600
    ):
        # Set in both caches
        self.memory_cache[key] = value
        await self.redis.setex(key, ttl, value)
```

### Database Query Optimization

```python
# Use prepared statements
prepared_query = await conn.prepare("""
    SELECT u.*, COUNT(m.id) as message_count
    FROM users u
    LEFT JOIN messages m ON u.id = m.user_id
    WHERE u.guild_id = $1
    GROUP BY u.id
    LIMIT $2 OFFSET $3
""")

# Execute with parameters
results = await prepared_query.fetch(guild_id, limit, offset)

# Use proper indexing
"""
CREATE INDEX CONCURRENTLY idx_messages_user_created 
ON messages(user_id, created_at DESC);
"""

# Batch operations
async def bulk_update_users(updates: List[Tuple[int, str]]):
    async with pool.acquire() as conn:
        await conn.executemany(
            "UPDATE users SET status = $2 WHERE id = $1",
            updates
        )
```

### Memory Management

```python
# Use weak references for caches
import weakref

class WeakCache:
    def __init__(self):
        self._cache = weakref.WeakValueDictionary()
    
    def get(self, key):
        return self._cache.get(key)
    
    def set(self, key, value):
        self._cache[key] = value

# Generator for large datasets
async def fetch_all_users_chunked(guild_id: int):
    offset = 0
    chunk_size = 100
    
    while True:
        users = await fetch_users(guild_id, offset, chunk_size)
        if not users:
            break
        
        for user in users:
            yield user
        
        offset += chunk_size
```

## Deployment Architecture

### Docker Configuration

```dockerfile
# Multi-stage build for smaller image
FROM python:3.11-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
CMD ["python", "-m", "bot.main"]
```

### Docker Compose Production

```yaml
version: '3.8'

services:
  bot:
    image: vsb-bot:latest
    restart: unless-stopped
    environment:
      - DISCORD_BOT_TOKEN=${DISCORD_BOT_TOKEN}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    networks:
      - internal
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G

  postgres:
    image: postgres:15-alpine
    restart: unless-stopped
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_PASSWORD_FILE=/run/secrets/db_password
    secrets:
      - db_password
    networks:
      - internal
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U vsb_bot"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    networks:
      - internal
    command: redis-server --appendonly yes

networks:
  internal:
    driver: bridge

volumes:
  postgres_data:

secrets:
  db_password:
    external: true
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vsb-bot
spec:
  replicas: 2
  selector:
    matchLabels:
      app: vsb-bot
  template:
    metadata:
      labels:
        app: vsb-bot
    spec:
      containers:
      - name: bot
        image: vsb-bot:latest
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1"
        env:
        - name: DISCORD_BOT_TOKEN
          valueFrom:
            secretKeyRef:
              name: vsb-bot-secrets
              key: discord-token
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
```

## Monitoring & Observability

### Health Check Implementation

```python
@app.route('/health')
async def health_check():
    """
    Comprehensive health check endpoint.
    """
    checks = {
        "bot": check_bot_status(),
        "database": check_database(),
        "redis": check_redis(),
        "discord": check_discord_connection()
    }
    
    all_healthy = all(check["healthy"] for check in checks.values())
    status_code = 200 if all_healthy else 503
    
    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }, status_code
```

### Metrics Collection

```python
from prometheus_client import Counter, Histogram, Gauge

# Define metrics
commands_total = Counter(
    'bot_commands_total',
    'Total number of commands executed',
    ['command', 'status']
)

command_duration = Histogram(
    'bot_command_duration_seconds',
    'Command execution duration',
    ['command']
)

active_users = Gauge(
    'bot_active_users',
    'Number of active users'
)

# Use in code
@command_duration.time()
async def execute_command(cmd):
    try:
        result = await cmd.execute()
        commands_total.labels(command=cmd.name, status='success').inc()
        return result
    except Exception as e:
        commands_total.labels(command=cmd.name, status='error').inc()
        raise
```

### Logging Architecture

```python
import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Use structured logging
logger.info(
    "command_executed",
    command="ban",
    user_id=12345,
    target_id=67890,
    reason="spam",
    duration=0.123
)
```

## Troubleshooting Guide

### Common Issues and Solutions

#### 1. Database Connection Issues

```python
# Symptom: asyncpg.exceptions.TooManyConnectionsError
# Solution: Increase max_connections in postgresql.conf
# Or reduce pool size in bot configuration

# Debug connection pool
async def debug_pool():
    pool = database_service.pool
    print(f"Pool size: {pool.get_size()}")
    print(f"Free connections: {pool.get_idle_size()}")
    print(f"Used connections: {pool.get_size() - pool.get_idle_size()}")
```

#### 2. Memory Leaks

```python
# Use memory profiler to identify leaks
from memory_profiler import profile

@profile
async def potentially_leaky_function():
    # Function code here
    pass

# Monitor memory usage
import psutil
import os

def log_memory_usage():
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    logger.info(
        "memory_usage",
        rss_mb=memory_info.rss / 1024 / 1024,
        vms_mb=memory_info.vms / 1024 / 1024
    )
```

#### 3. Discord Rate Limits

```python
# Handle rate limits gracefully
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(
            f"Command on cooldown. Try again in {error.retry_after:.2f}s",
            delete_after=5
        )
    elif isinstance(error, discord.HTTPException):
        if error.status == 429:  # Rate limited
            logger.warning("Rate limited", endpoint=error.text)
            await asyncio.sleep(error.retry_after)
```

#### 4. Async Deadlocks

```python
# Avoid deadlocks with timeout
async def safe_operation():
    try:
        async with asyncio.timeout(30):
            result = await long_running_operation()
            return result
    except asyncio.TimeoutError:
        logger.error("Operation timed out")
        return None
```

### Debug Commands

```python
@app_commands.command(name="debug")
@app_commands.check(is_developer)
async def debug_command(interaction: discord.Interaction):
    """Admin debug command for troubleshooting."""
    
    stats = {
        "Latency": f"{bot.latency * 1000:.2f}ms",
        "Guilds": len(bot.guilds),
        "Users": len(bot.users),
        "Cogs": len(bot.cogs),
        "Commands": len(bot.tree.get_commands()),
        "DB Pool": f"{db.pool.get_size()}/{db.pool.get_idle_size()} (total/idle)",
        "Memory": f"{psutil.Process().memory_info().rss / 1024 / 1024:.2f} MB",
        "Uptime": str(datetime.now() - bot.start_time)
    }
    
    embed = discord.Embed(title="Debug Information", color=discord.Color.blue())
    for key, value in stats.items():
        embed.add_field(name=key, value=value, inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)
```

### Performance Profiling

```python
import cProfile
import pstats
from io import StringIO

def profile_function(func):
    """Decorator for profiling async functions."""
    async def wrapper(*args, **kwargs):
        profiler = cProfile.Profile()
        profiler.enable()
        
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            profiler.disable()
            
            stream = StringIO()
            stats = pstats.Stats(profiler, stream=stream)
            stats.sort_stats('cumulative')
            stats.print_stats(10)
            
            logger.debug("Profile results", profile=stream.getvalue())
    
    return wrapper
```

---

This technical guide provides comprehensive documentation of the VSB Discord Bot's architecture, implementation details, and operational procedures. For specific implementation questions or advanced troubleshooting, consult the inline code documentation or contact the development team.