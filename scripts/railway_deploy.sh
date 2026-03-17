#!/bin/bash
# ============================================================================
# Railway Deployment Script for sanjai-insight
# ============================================================================
# 용도: Railway CLI를 통한 배포 자동화
# 실행: ./scripts/railway_deploy.sh
# ============================================================================

set -e  # Exit on error
set -u  # Exit on undefined variable

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================================================
# Configuration
# ============================================================================
PROJECT_NAME="sanjai-insight"
REQUIRED_COMMANDS=("railway" "git")
REQUIRED_ENV_VARS=(
    "TELEGRAM_BOT_TOKEN"
    "TELEGRAM_CEO_CHAT_ID"
    "ANTHROPIC_API_KEY"
    "DATABASE_PATH"
    "MONTHLY_BUDGET_KRW"
)

# ============================================================================
# Functions
# ============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "Command '$1' not found. Please install it first."
        exit 1
    fi
}

check_railway_env() {
    log_info "Checking Railway environment variables..."

    missing_vars=()
    for var in "${REQUIRED_ENV_VARS[@]}"; do
        if ! railway variables get "$var" &> /dev/null; then
            missing_vars+=("$var")
        fi
    done

    if [ ${#missing_vars[@]} -gt 0 ]; then
        log_error "Missing required environment variables in Railway:"
        for var in "${missing_vars[@]}"; do
            echo "  - $var"
        done
        log_warn "Please set them using: railway variables set KEY=VALUE"
        exit 1
    fi

    log_info "All required environment variables are set."
}

# ============================================================================
# Pre-deployment Checks
# ============================================================================

log_info "Starting Railway deployment for $PROJECT_NAME..."
echo ""

# Check required commands
log_info "Checking required commands..."
for cmd in "${REQUIRED_COMMANDS[@]}"; do
    check_command "$cmd"
done
log_info "All required commands are available."
echo ""

# Check Railway login
log_info "Checking Railway login status..."
if ! railway whoami &> /dev/null; then
    log_error "Not logged in to Railway. Please run: railway login"
    exit 1
fi
log_info "Railway login OK: $(railway whoami)"
echo ""

# Check Railway project
log_info "Checking Railway project..."
if ! railway status &> /dev/null; then
    log_error "Not linked to a Railway project. Please run: railway link"
    exit 1
fi
log_info "Railway project: $(railway status | head -n 1)"
echo ""

# Check git status
log_info "Checking git status..."
if [[ -n $(git status -s) ]]; then
    log_warn "Uncommitted changes detected:"
    git status -s
    echo ""
    read -p "Continue deployment with uncommitted changes? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Deployment cancelled."
        exit 0
    fi
else
    log_info "Working directory is clean."
fi
echo ""

# Check Railway environment variables
check_railway_env
echo ""

# ============================================================================
# Deployment
# ============================================================================

log_info "Starting deployment..."
echo ""

# Deploy to Railway
log_info "Deploying to Railway..."
railway up -d

log_info "Deployment initiated successfully!"
echo ""

# ============================================================================
# Post-deployment
# ============================================================================

log_info "Waiting for deployment to complete (30s)..."
sleep 30
echo ""

# Check deployment status
log_info "Checking deployment status..."
railway status

echo ""
log_info "Deployment process complete!"
echo ""

# Show logs
log_info "Fetching recent logs..."
railway logs --limit 20

echo ""
log_info "========================================="
log_info "Deployment Summary"
log_info "========================================="
log_info "Project: $PROJECT_NAME"
log_info "Status: $(railway status | head -n 1)"
log_info ""
log_info "Next steps:"
log_info "1. Monitor logs: railway logs"
log_info "2. Check health: curl https://YOUR_DOMAIN/healthz"
log_info "3. View metrics: curl https://YOUR_DOMAIN/metrics"
log_info "========================================="
