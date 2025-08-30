# Contributing to VSB Discord Moderation Bot

Thank you for your interest in contributing to the VSB Discord Moderation Bot! This document provides guidelines and instructions for contributing to the project.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Contribution Process](#contribution-process)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Pull Request Process](#pull-request-process)
- [Issue Guidelines](#issue-guidelines)
- [Community](#community)

## Code of Conduct

### Our Pledge

We as members, contributors, and leaders pledge to make participation in our community a harassment-free experience for everyone, regardless of age, body size, visible or invisible disability, ethnicity, sex characteristics, gender identity and expression, level of experience, education, socio-economic status, nationality, personal appearance, race, caste, color, religion, or sexual identity and orientation.

### Our Standards

**Examples of behavior that contributes to a positive environment:**
- Using welcoming and inclusive language
- Being respectful of differing viewpoints and experiences
- Gracefully accepting constructive criticism
- Focusing on what is best for the community
- Showing empathy towards other community members

**Examples of unacceptable behavior:**
- The use of sexualized language or imagery
- Trolling, insulting/derogatory comments, and personal attacks
- Public or private harassment
- Publishing others' private information without permission
- Other conduct which could reasonably be considered inappropriate

### Enforcement

Instances of abusive, harassing, or otherwise unacceptable behavior may be reported to the project team at conduct@vsb-bot.example.com. All complaints will be reviewed and investigated promptly and fairly.

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Docker 24.0 or higher
- PostgreSQL 15 (for local development without Docker)
- Git
- A Discord account and test server
- Basic understanding of Discord.py and asyncio

### First-Time Contributors

1. Look for issues labeled `good first issue` or `help wanted`
2. Comment on the issue to express your interest
3. Wait for assignment before starting work
4. Ask questions if you need clarification

## Development Setup

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR_USERNAME/py_VSB_Discord_Moderation_BOT.git
cd py_VSB_Discord_Moderation_BOT

# Add upstream remote
git remote add upstream https://github.com/KasheK420/py_VSB_Discord_Moderation_BOT.git
```

### 2. Create Development Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Copy environment template
cp .env.example .env.development
# Edit .env.development with your test bot tokens
```

### 3. Setup Docker Development

```bash
# Start development environment
make dev-up

# Check logs
make dev-logs

# Run database migrations
make migrate
```

### 4. Create Test Discord Server

1. Create a new Discord server for testing
2. Create a bot application at https://discord.com/developers
3. Add bot to your test server with required permissions
4. Configure `.env.development` with your bot token and server ID

## Contribution Process

### 1. Find or Create an Issue

- Check existing issues before creating a new one
- Clearly describe the problem or feature request
- Wait for maintainer feedback before starting major work

### 2. Create a Feature Branch

```bash
# Update your fork
git checkout main
git pull upstream main
git push origin main

# Create feature branch
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-number-description
```

### 3. Make Your Changes

- Write clean, readable code
- Follow the coding standards
- Add/update tests as needed
- Update documentation
- Keep commits atomic and well-described

### 4. Test Your Changes

```bash
# Run tests locally
make test

# Check code quality
make lint

# Test in Docker environment
make dev-up
make dev-logs
```

### 5. Submit Pull Request

- Push your branch to your fork
- Create a pull request against `main` branch
- Fill out the PR template completely
- Link related issues
- Wait for review

## Coding Standards

### Python Style Guide

We follow PEP 8 with some modifications:

```python
# bot/services/example_service.py
"""
Module docstring describing the service.
"""

import asyncio
from typing import Optional, List, Dict, Any
import discord
from discord.ext import commands

# Constants in UPPER_CASE
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30

class ExampleService:
    """
    Class docstring with description.
    
    Attributes:
        bot: The Discord bot instance
        config: Service configuration
    """
    
    def __init__(self, bot: commands.Bot, config: Dict[str, Any]):
        """Initialize the service."""
        self.bot = bot
        self.config = config
        self._cache: Dict[int, Any] = {}
    
    async def process_message(self, message: discord.Message) -> Optional[str]:
        """
        Process a Discord message.
        
        Args:
            message: The Discord message to process
            
        Returns:
            Processed result or None if skipped
            
        Raises:
            ValueError: If message content is invalid
        """
        if not message.content:
            return None
            
        # Use descriptive variable names
        processed_content = await self._process_content(message.content)
        
        # Add logging for important operations
        logger.info(f"Processed message {message.id}: {processed_content[:50]}")
        
        return processed_content
    
    async def _process_content(self, content: str) -> str:
        """Private method for internal processing."""
        # Implementation here
        return content.upper()
```

### Database Conventions

```python
# bot/database/models/example.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Example:
    """Database model for examples table."""
    id: int
    name: str
    value: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    @classmethod
    def from_row(cls, row: dict) -> 'Example':
        """Create instance from database row."""
        return cls(
            id=row['id'],
            name=row['name'],
            value=row.get('value'),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )
```

### Discord Cog Structure

```python
# bot/cogs/example_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)

class ExampleCog(commands.Cog):
    """Cog description."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db_service
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Called when cog is ready."""
        logger.info("ExampleCog ready")
    
    @app_commands.command(name="example", description="Example command")
    @app_commands.describe(param="Parameter description")
    async def example_command(
        self, 
        interaction: discord.Interaction,
        param: str
    ):
        """Handle example slash command."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            result = await self._process_example(param)
            await interaction.followup.send(f"Result: {result}")
        except Exception as e:
            logger.error(f"Error in example command: {e}")
            await interaction.followup.send("An error occurred.")
    
    async def _process_example(self, param: str) -> str:
        """Process example logic."""
        return param.upper()

async def setup(bot: commands.Bot):
    """Setup function for cog loading."""
    await bot.add_cog(ExampleCog(bot))
```

### Commit Message Format

```
type(scope): subject

body

footer
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Test additions or changes
- `chore`: Build process or auxiliary tool changes
- `perf`: Performance improvements

**Examples:**
```
feat(economy): add daily reward system

Implemented a daily reward system that gives users points
once every 24 hours. Includes cooldown tracking and 
database persistence.

Closes #123
```

```
fix(moderation): resolve timeout command permission issue

Fixed an issue where the timeout command was not checking
for proper permissions before execution.

Fixes #456
```

## Testing Guidelines

### Writing Tests

```python
# tests/test_example_service.py
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from bot.services.example_service import ExampleService

@pytest.fixture
async def service():
    """Create test service instance."""
    bot_mock = Mock()
    bot_mock.user = Mock(id=123456)
    return ExampleService(bot_mock, {})

@pytest.mark.asyncio
async def test_process_message_empty(service):
    """Test processing empty message."""
    message = Mock(content="")
    result = await service.process_message(message)
    assert result is None

@pytest.mark.asyncio
async def test_process_message_valid(service):
    """Test processing valid message."""
    message = Mock(content="test message")
    result = await service.process_message(message)
    assert result == "TEST MESSAGE"

@pytest.mark.asyncio
async def test_database_operation():
    """Test database operations."""
    with patch('bot.database.database_service.pool') as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_conn.fetchrow.return_value = {'id': 1, 'name': 'test'}
        
        # Test your database operation
        # Assert expected behavior
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=bot --cov-report=html

# Run specific test file
pytest tests/test_example_service.py

# Run with verbose output
pytest -v

# Run only marked tests
pytest -m "not slow"
```

### Test Categories

Mark your tests appropriately:

```python
@pytest.mark.unit        # Fast unit tests
@pytest.mark.integration # Integration tests
@pytest.mark.slow        # Slow tests
@pytest.mark.api         # External API tests
```

## Pull Request Process

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Tests pass locally
- [ ] Added new tests
- [ ] Updated existing tests

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No new warnings
- [ ] Related issues linked
```

### Review Process

1. **Automated Checks**: Must pass all CI/CD checks
2. **Code Review**: At least one maintainer approval required
3. **Testing**: Evidence of testing required for non-trivial changes
4. **Documentation**: Must be updated for API changes

### Merge Criteria

- All checks passing
- Approved by maintainer
- No unresolved conversations
- Up to date with main branch
- Follows semantic versioning

## Issue Guidelines

### Bug Reports

```markdown
**Describe the bug**
Clear description of the issue

**To Reproduce**
1. Step one
2. Step two
3. See error

**Expected behavior**
What should happen

**Screenshots**
If applicable

**Environment**
- OS: [e.g., Ubuntu 22.04]
- Python: [e.g., 3.11.5]
- Bot version: [e.g., 1.0.0]

**Additional context**
Any other relevant information
```

### Feature Requests

```markdown
**Is your feature request related to a problem?**
Description of the problem

**Describe the solution**
Your proposed solution

**Alternatives considered**
Other solutions you've considered

**Additional context**
Any other information
```

## Community

### Communication Channels

- **Discord**: [VSB Development Server](https://discord.gg/vsb-dev)
- **GitHub Discussions**: For general questions and ideas
- **Issues**: For bugs and feature requests
- **Email**: dev@vsb-bot.example.com

### Getting Help

- Check documentation first
- Search existing issues
- Ask in Discord #dev-help channel
- Create a discussion for general questions

### Recognition

Contributors are recognized in:
- CONTRIBUTORS.md file
- Release notes
- Discord bot credits command
- Annual contributor spotlight

## Advanced Topics

### Adding New Services

1. Create service file in `bot/services/`
2. Implement service class with required methods
3. Register in `service_loader.py`
4. Add configuration to `.env.example`
5. Update documentation
6. Add tests

### Database Migrations

```bash
# Create new migration
make migration

# Apply migrations
make migrate

# Rollback migration
docker compose exec bot alembic downgrade -1
```

### Performance Considerations

- Use asyncio properly (avoid blocking operations)
- Implement caching where appropriate
- Use database connection pooling
- Profile code for bottlenecks
- Consider rate limits for external APIs

### Security Guidelines

- Never commit secrets or tokens
- Validate all user input
- Use parameterized queries
- Implement rate limiting
- Follow OWASP guidelines
- Report security issues privately

## Thank You!

Thank you for contributing to VSB Discord Bot! Your efforts help make this project better for everyone in the community.