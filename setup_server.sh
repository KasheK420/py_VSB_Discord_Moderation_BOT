#!/bin/bash

# VSB Discord Bot - Self-Hosted GitHub Runner Setup Script
# Ubuntu 22.04 LTS
# Run with: sudo ./setup_server.sh

set -euo pipefail

# Configuration
BOT_USER="botuser"
BOT_DIR="/opt/discord-bot"
REPO_URL="https://github.com/KasheK420/py_VSB_Discord_Moderation_BOT.git"
LOG_FILE="/var/log/bot_setup.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
    log "INFO: $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
    log "SUCCESS: $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    log "WARNING: $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    log "ERROR: $1"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   print_error "This script must be run as root (use sudo)"
   exit 1
fi

print_status "Starting VSB Discord Bot self-hosted runner setup..."

# Update system
print_status "Updating system packages..."
apt update && apt upgrade -y
apt install -y curl wget git ufw fail2ban unattended-upgrades apt-transport-https ca-certificates gnupg lsb-release jq

# Install Docker
print_status "Installing Docker..."
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Install Docker Compose v2
print_status "Installing Docker Compose..."
DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)
curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose

# Create bot user
print_status "Creating bot user..."
if ! id "$BOT_USER" &>/dev/null; then
    useradd -r -d "$BOT_DIR" -s /bin/bash "$BOT_USER"
    usermod -aG docker "$BOT_USER"
fi

# Create GitHub Actions runner user
print_status "Creating GitHub Actions runner user..."
if ! id "github-runner" &>/dev/null; then
    useradd -m -s /bin/bash github-runner
    usermod -aG docker github-runner
    usermod -aG sudo github-runner
    # Allow github-runner to sudo without password for deployment commands
    echo "github-runner ALL=(ALL) NOPASSWD: /bin/systemctl start discord-bot, /bin/systemctl stop discord-bot, /bin/systemctl restart discord-bot, /bin/systemctl status discord-bot, /usr/local/bin/docker-compose, /usr/bin/docker-compose, /usr/bin/docker" >> /etc/sudoers
fi

# Create directories
print_status "Creating application directories..."
mkdir -p "$BOT_DIR"/{data,logs,backups,nginx,monitoring}
mkdir -p "$BOT_DIR"/monitoring/{prometheus,grafana/{dashboards,datasources}}

# Create GitHub Actions runner directory
mkdir -p /home/github-runner/actions-runner
chown -R github-runner:github-runner /home/github-runner

# Clone repository
print_status "Cloning repository..."
if [ -d "$BOT_DIR" ]; then
    print_status "Removing existing directory..."
    rm -rf "$BOT_DIR"
fi
sudo -u "$BOT_USER" git clone "$REPO_URL" "$BOT_DIR"

# Set permissions
chown -R "$BOT_USER":"$BOT_USER" "$BOT_DIR"
chmod -R 755 "$BOT_DIR"

# Configure firewall
print_status "Configuring firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw allow 8081/tcp  # Health check
ufw allow 9090/tcp  # Prometheus (optional)
ufw allow 3000/tcp  # Grafana (optional)
ufw --force enable

# Configure fail2ban
print_status "Configuring fail2ban..."
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true
port = ssh
logpath = %(sshd_log)s
backend = %(sshd_backend)s

[docker-auth]
enabled = true
filter = docker-auth
logpath = /var/log/docker.log
maxretry = 3
bantime = 3600
EOF

# Create fail2ban filter for Docker
cat > /etc/fail2ban/filter.d/docker-auth.conf << 'EOF'
[Definition]
failregex = ^.*\[error\].*authentication failed.*client: <HOST>.*$
ignoreregex =
EOF

systemctl enable fail2ban
systemctl restart fail2ban

# Configure automatic security updates
print_status "Configuring automatic security updates..."
cat > /etc/apt/apt.conf.d/50unattended-upgrades << 'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
};

Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
EOF

cat > /etc/apt/apt.conf.d/20auto-upgrades << 'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
EOF

# Install GitHub Actions runner
print_status "Installing GitHub Actions runner..."
cd /home/github-runner/actions-runner

# Download the latest runner package
RUNNER_VERSION=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | grep 'tag_name' | cut -d\" -f4 | sed 's/v//')
curl -o actions-runner-linux-x64.tar.gz -L "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"

# Extract the installer
tar xzf ./actions-runner-linux-x64.tar.gz
chown -R github-runner:github-runner /home/github-runner/actions-runner

# Create systemd service for the bot
print_status "Creating systemd service..."
cat > /etc/systemd/system/discord-bot.service << EOF
[Unit]
Description=VSB Discord Bot
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=true
WorkingDirectory=$BOT_DIR
User=$BOT_USER
Group=$BOT_USER

# Start command
ExecStart=/usr/local/bin/docker-compose -f docker-compose.production.yml up -d

# Stop command
ExecStop=/usr/local/bin/docker-compose -f docker-compose.production.yml down

# Restart policy
Restart=on-failure
RestartSec=10

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$BOT_DIR

[Install]
WantedBy=multi-user.target
EOF

# Create GitHub Actions runner service
cat > /etc/systemd/system/github-runner.service << 'EOF'
[Unit]
Description=GitHub Actions Runner
After=network.target

[Service]
Type=simple
User=github-runner
WorkingDirectory=/home/github-runner/actions-runner
ExecStart=/home/github-runner/actions-runner/run.sh
Restart=always
RestartSec=5
KillMode=process
KillSignal=SIGTERM
TimeoutStopSec=5min

[Install]
WantedBy=multi-user.target
EOF

# Create nginx configuration
print_status "Creating nginx configuration..."
cat > "$BOT_DIR"/nginx/nginx.conf << 'EOF'
events {
    worker_connections 1024;
}

http {
    upstream discord_bot {
        server discord-bot:8081;
    }

    server {
        listen 80;
        server_name _;

        location /health {
            proxy_pass http://discord_bot/health;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        location /status {
            proxy_pass http://discord_bot/status;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        location /metrics {
            proxy_pass http://discord_bot/metrics;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        location / {
            return 301 https://$server_name$request_uri;
        }
    }
}
EOF

# Create monitoring configuration
print_status "Creating monitoring configuration..."
cat > "$BOT_DIR"/monitoring/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'discord-bot'
    static_configs:
      - targets: ['discord-bot:8081']
    metrics_path: '/metrics'
    scrape_interval: 30s

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['localhost:9100']
EOF

# Create backup script
print_status "Creating backup script..."
cat > "$BOT_DIR"/backup.sh << 'EOF'
#!/bin/bash

BACKUP_DIR="/opt/discord-bot/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_FILE="/opt/discord-bot/data/bot_database.db"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Create backup
if [ -f "$DB_FILE" ]; then
    cp "$DB_FILE" "$BACKUP_DIR/bot_database_$DATE.db"
    
    # Compress backup
    gzip "$BACKUP_DIR/bot_database_$DATE.db"
    
    # Remove backups older than 30 days
    find "$BACKUP_DIR" -name "*.gz" -mtime +30 -delete
    
    echo "Backup completed: bot_database_$DATE.db.gz"
else
    echo "Database file not found: $DB_FILE"
fi
EOF

chmod +x "$BOT_DIR"/backup.sh
chown "$BOT_USER":"$BOT_USER" "$BOT_DIR"/backup.sh

# Create cron job for backups
print_status "Setting up automatic backups..."
(crontab -u "$BOT_USER" -l 2>/dev/null; echo "0 2 * * * /opt/discord-bot/backup.sh >> /opt/discord-bot/logs/backup.log 2>&1") | crontab -u "$BOT_USER" -

# Create health check script
print_status "Creating health check script..."
cat > "$BOT_DIR"/health_check.sh << 'EOF'
#!/bin/bash

# Health check script for Discord bot
BOT_DIR="/opt/discord-bot"
LOG_FILE="$BOT_DIR/logs/health_check.log"

# Create log directory if it doesn't exist
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# Check if containers are running
if docker-compose -f "$BOT_DIR/docker-compose.production.yml" ps | grep -q "Up"; then
    log "✓ Containers are running"
    
    # Check health endpoint
    if curl -f http://localhost:8081/health >/dev/null 2>&1; then
        log "✓ Health endpoint responding"
        exit 0
    else
        log "✗ Health endpoint not responding"
        exit 1
    fi
else
    log "✗ Containers not running"
    exit 1
fi
EOF

chmod +x "$BOT_DIR"/health_check.sh
chown "$BOT_USER":"$BOT_USER" "$BOT_DIR"/health_check.sh

# Setup log rotation
print_status "Setting up log rotation..."
cat > /etc/logrotate.d/discord-bot << 'EOF'
/opt/discord-bot/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 botuser botuser
    postrotate
        docker kill --signal="USR1" vsb-discord-bot 2>/dev/null || true
    endscript
}
EOF

# Create deployment script for GitHub Actions
print_status "Creating deployment script..."
cat > "$BOT_DIR"/deploy.sh << 'EOF'
#!/bin/bash

set -e

BOT_DIR="/opt/discord-bot"
LOG_FILE="$BOT_DIR/logs/deployment.log"

# Create log directory if it doesn't exist
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

log "Starting deployment..."

# Pull latest changes
cd "$BOT_DIR"
git pull origin main

# Stop current services
log "Stopping current services..."
sudo systemctl stop discord-bot || true

# Pull latest Docker images
log "Pulling latest Docker images..."
docker-compose -f docker-compose.production.yml pull

# Start services
log "Starting services..."
sudo systemctl start discord-bot

# Wait for services to be ready
log "Waiting for services to be ready..."
sleep 30

# Health check
for i in {1..10}; do
    if curl -f http://localhost:8081/health >/dev/null 2>&1; then
        log "✓ Health check passed"
        break
    fi
    if [ $i -eq 10 ]; then
        log "✗ Health check failed after 10 attempts"
        exit 1
    fi
    sleep 10
done

# Clean up old images
log "Cleaning up old Docker images..."
docker image prune -f

log "Deployment completed successfully"
EOF

chmod +x "$BOT_DIR"/deploy.sh
chown github-runner:github-runner "$BOT_DIR"/deploy.sh

# Enable and start services
print_status "Enabling services..."
systemctl daemon-reload
systemctl enable discord-bot
systemctl enable docker

# Final setup
chown -R "$BOT_USER":"$BOT_USER" "$BOT_DIR"

print_success "Server setup completed!"
print_warning "IMPORTANT: Next steps to complete setup:"
echo ""
echo "1. Configure GitHub Actions runner:"
echo "   sudo -u github-runner /home/github-runner/actions-runner/config.sh --url https://github.com/KasheK420/py_VSB_Discord_Moderation_BOT --token YOUR_RUNNER_TOKEN"
echo ""
echo "2. Start GitHub Actions runner:"
echo "   sudo systemctl enable github-runner"
echo "   sudo systemctl start github-runner"
echo ""
echo "3. Configure GitHub repository secrets (environment variables)"
echo ""
echo "4. Push to main branch to trigger first deployment"
echo ""
echo "5. Check health:"
echo "   curl http://localhost:8081/health"
echo ""
print_warning "GitHub runner token can be obtained from:"
echo "https://github.com/KasheK420/py_VSB_Discord_Moderation_BOT/settings/actions/runners/new"
echo ""
print_success "Setup log saved to: $LOG_FILE"