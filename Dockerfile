# Production Dockerfile for VSB Discord Bot
# Place this file in: /Dockerfile (repository root)

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-root user for security
RUN groupadd -r botuser && useradd -r -g botuser botuser

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set work directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bot/ ./bot/
COPY pyproject.toml .

# Create necessary directories with proper permissions
RUN mkdir -p /app/data /app/logs /app/backups \
    && chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8081/health', timeout=5)" || exit 1

# Expose health check port
EXPOSE 8081

# Set the entry point
CMD ["python", "-m", "bot.app"]