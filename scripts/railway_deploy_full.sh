#!/bin/bash
# ============================================================================
# Railway 완전 자동화 배포 스크립트 (Blue-Green + Rollback + 검증)
# ============================================================================
# 용도: Railway 배포 전체 라이프사이클 자동화
# 실행: ./scripts/railway_deploy_full.sh [--blue-green] [--skip-tests] [--notify]
# ============================================================================

set -e  # Exit on error
set -u  # Exit on undefined variable
set -o pipefail  # Pipe failures are errors

# ============================================================================
# Configuration
# ============================================================================

PROJECT_NAME="sanjai-insight"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
DEPLOY_LOG="$LOG_DIR/deploy_$(date +%Y%m%d_%H%M%S).log"
HEALTHCHECK_RETRIES=10
HEALTHCHECK_INTERVAL=5
ROLLBACK_SNAPSHOT=""
BLUE_GREEN_MODE=false
SKIP_TESTS=false
NOTIFY_ENABLED=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Required commands
REQUIRED_COMMANDS=("railway" "git" "curl" "python3")

# Required environment variables
REQUIRED_ENV_VARS=(
    "TELEGRAM_BOT_TOKEN"
    "TELEGRAM_CEO_CHAT_ID"
    "ANTHROPIC_API_KEY"
    "DATABASE_PATH"
    "MONTHLY_BUDGET_KRW"
)

# ============================================================================
# Logging Functions
# ============================================================================

mkdir -p "$LOG_DIR"

log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" | tee -a "$DEPLOY_LOG"
}

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*" | tee -a "$DEPLOY_LOG"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*" | tee -a "$DEPLOY_LOG"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" | tee -a "$DEPLOY_LOG"
}

log_debug() {
    echo -e "${CYAN}[DEBUG]${NC} $*" | tee -a "$DEPLOY_LOG"
}

log_section() {
    echo "" | tee -a "$DEPLOY_LOG"
    echo -e "${BLUE}========================================${NC}" | tee -a "$DEPLOY_LOG"
    echo -e "${BLUE}$*${NC}" | tee -a "$DEPLOY_LOG"
    echo -e "${BLUE}========================================${NC}" | tee -a "$DEPLOY_LOG"
}

# ============================================================================
# Notification Functions
# ============================================================================

send_notification() {
    if [ "$NOTIFY_ENABLED" = false ]; then
        return 0
    fi

    local title=$1
    local message=$2
    local level=${3:-info}  # info, warning, error

    # Telegram 알림
    if [ -n "${TELEGRAM_CEO_CHAT_ID:-}" ] && [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
        local emoji="ℹ️"
        case $level in
            warning) emoji="⚠️" ;;
            error) emoji="❌" ;;
            success) emoji="✅" ;;
        esac

        local text="$emoji *$title*%0A%0A$message"
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CEO_CHAT_ID}" \
            -d "text=$text" \
            -d "parse_mode=Markdown" > /dev/null || log_warn "Telegram 알림 실패"
    fi
}

# ============================================================================
# Argument Parsing
# ============================================================================

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --blue-green)
                BLUE_GREEN_MODE=true
                log_info "Blue-Green 배포 모드 활성화"
                shift
                ;;
            --skip-tests)
                SKIP_TESTS=true
                log_warn "테스트 스킵 (프로덕션 비권장)"
                shift
                ;;
            --notify)
                NOTIFY_ENABLED=true
                log_info "알림 활성화"
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                echo "Usage: $0 [--blue-green] [--skip-tests] [--notify]"
                exit 1
                ;;
        esac
    done
}

# ============================================================================
# Pre-flight Checks
# ============================================================================

check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "Command '$1' not found. Please install it first."
        exit 1
    fi
}

check_commands() {
    log_section "Pre-flight: Command Check"
    for cmd in "${REQUIRED_COMMANDS[@]}"; do
        check_command "$cmd"
        log_info "✓ $cmd"
    done
}

check_railway_auth() {
    log_section "Pre-flight: Railway Auth"
    if ! railway whoami &> /dev/null; then
        log_error "Not logged in to Railway. Run: railway login"
        exit 1
    fi
    local user=$(railway whoami 2>&1)
    log_info "✓ Railway user: $user"
}

check_railway_project() {
    log_section "Pre-flight: Railway Project"
    if ! railway status &> /dev/null; then
        log_error "Not linked to Railway project. Run: railway link"
        exit 1
    fi
    local status=$(railway status 2>&1 | head -n 1)
    log_info "✓ Railway project: $status"
}

check_git_status() {
    log_section "Pre-flight: Git Status"

    # Check uncommitted changes
    if [[ -n $(git status -s) ]]; then
        log_warn "Uncommitted changes detected:"
        git status -s | tee -a "$DEPLOY_LOG"
        log_error "Commit all changes before deployment"
        exit 1
    fi

    # Check unpushed commits
    local unpushed=$(git log @{u}.. --oneline 2>&1)
    if [ -n "$unpushed" ]; then
        log_warn "Unpushed commits detected:"
        echo "$unpushed" | tee -a "$DEPLOY_LOG"
        log_error "Push all commits before deployment"
        exit 1
    fi

    log_info "✓ Git status clean"

    # Store current commit for rollback
    ROLLBACK_SNAPSHOT=$(git rev-parse HEAD)
    log_debug "Rollback snapshot: $ROLLBACK_SNAPSHOT"
}

check_railway_env() {
    log_section "Pre-flight: Railway Environment"

    local missing_vars=()
    for var in "${REQUIRED_ENV_VARS[@]}"; do
        if ! railway variables get "$var" &> /dev/null 2>&1; then
            missing_vars+=("$var")
        else
            log_info "✓ $var"
        fi
    done

    if [ ${#missing_vars[@]} -gt 0 ]; then
        log_error "Missing required environment variables:"
        for var in "${missing_vars[@]}"; do
            echo "  - $var" | tee -a "$DEPLOY_LOG"
        done
        log_error "Set them using: railway variables set KEY=VALUE"
        exit 1
    fi
}

run_tests() {
    if [ "$SKIP_TESTS" = true ]; then
        log_warn "테스트 스킵됨"
        return 0
    fi

    log_section "Pre-flight: Running Tests"

    cd "$PROJECT_ROOT"

    if [ ! -f "pyproject.toml" ]; then
        log_warn "pyproject.toml not found, skipping tests"
        return 0
    fi

    # Run pytest with coverage
    if python3 -m pytest tests/ -v --tb=short 2>&1 | tee -a "$DEPLOY_LOG"; then
        log_info "✓ All tests passed"
    else
        log_error "Tests failed. Fix errors before deployment."
        exit 1
    fi
}

check_database_backup() {
    log_section "Pre-flight: Database Backup"

    if [ -f "$PROJECT_ROOT/scripts/backup.sh" ]; then
        log_info "Creating pre-deployment backup..."
        if bash "$PROJECT_ROOT/scripts/backup.sh" 2>&1 | tee -a "$DEPLOY_LOG"; then
            log_info "✓ Backup created"
        else
            log_warn "Backup failed (non-critical)"
        fi
    else
        log_warn "backup.sh not found, skipping backup"
    fi
}

# ============================================================================
# Deployment Functions
# ============================================================================

deploy_standard() {
    log_section "Deployment: Standard Mode"

    log_info "Starting Railway deployment..."
    if railway up -d 2>&1 | tee -a "$DEPLOY_LOG"; then
        log_info "✓ Deployment initiated"
    else
        log_error "Deployment failed"
        return 1
    fi

    log_info "Waiting for deployment to stabilize..."
    sleep 30
}

deploy_blue_green() {
    log_section "Deployment: Blue-Green Mode"

    log_info "Blue-Green deployment requires manual Railway setup"
    log_info "Creating new deployment alongside current..."

    # Deploy to staging environment first
    log_info "Step 1: Deploy to staging"
    railway up -d --environment staging 2>&1 | tee -a "$DEPLOY_LOG" || return 1

    log_info "Step 2: Verify staging health"
    sleep 30

    # Health check on staging
    local staging_url=$(railway domain --environment staging 2>&1 | grep -oP 'https://[^\s]+' | head -n 1)
    if [ -n "$staging_url" ]; then
        if curl -f -s "$staging_url/healthz" > /dev/null; then
            log_info "✓ Staging health check passed"
        else
            log_error "Staging health check failed"
            return 1
        fi
    fi

    log_info "Step 3: Switch traffic to new deployment"
    log_warn "Manual traffic switch required in Railway dashboard"
    log_info "Old deployment remains available for rollback"
}

# ============================================================================
# Post-deployment Verification
# ============================================================================

get_deployment_url() {
    # Try to get deployment URL from Railway
    local url=$(railway domain 2>&1 | grep -oP 'https://[^\s]+' | head -n 1)
    echo "$url"
}

check_deployment_health() {
    log_section "Post-deployment: Health Check"

    local url=$(get_deployment_url)
    if [ -z "$url" ]; then
        log_warn "Could not determine deployment URL"
        return 0
    fi

    log_info "Deployment URL: $url"

    local retry=0
    while [ $retry -lt $HEALTHCHECK_RETRIES ]; do
        log_info "Health check attempt $((retry+1))/$HEALTHCHECK_RETRIES..."

        if curl -f -s "$url/healthz" > /dev/null 2>&1; then
            log_info "✓ Health check passed"
            return 0
        fi

        retry=$((retry+1))
        if [ $retry -lt $HEALTHCHECK_RETRIES ]; then
            sleep $HEALTHCHECK_INTERVAL
        fi
    done

    log_error "Health check failed after $HEALTHCHECK_RETRIES attempts"
    return 1
}

check_deployment_status() {
    log_section "Post-deployment: Status Check"

    local url=$(get_deployment_url)
    if [ -z "$url" ]; then
        log_warn "Could not determine deployment URL"
        return 0
    fi

    # Check /status endpoint
    local status_response=$(curl -s "$url/status" 2>&1)
    if [ -n "$status_response" ]; then
        log_info "Status endpoint response:"
        echo "$status_response" | python3 -m json.tool 2>&1 | tee -a "$DEPLOY_LOG"
    fi
}

check_deployment_metrics() {
    log_section "Post-deployment: Metrics Check"

    local url=$(get_deployment_url)
    if [ -z "$url" ]; then
        log_warn "Could not determine deployment URL"
        return 0
    fi

    # Check /metrics endpoint
    local metrics=$(curl -s "$url/metrics" 2>&1)
    if [ -n "$metrics" ]; then
        log_info "Metrics snapshot:"
        echo "$metrics" | head -n 20 | tee -a "$DEPLOY_LOG"
    fi
}

fetch_recent_logs() {
    log_section "Post-deployment: Recent Logs"

    log_info "Fetching last 50 log lines..."
    railway logs --limit 50 2>&1 | tee -a "$DEPLOY_LOG"
}

# ============================================================================
# Rollback Functions
# ============================================================================

rollback() {
    log_section "ROLLBACK: Reverting Deployment"

    send_notification "🔄 Rollback Initiated" "Deployment failed, reverting to $ROLLBACK_SNAPSHOT" "warning"

    if [ -z "$ROLLBACK_SNAPSHOT" ]; then
        log_error "No rollback snapshot available"
        return 1
    fi

    log_info "Rolling back to commit: $ROLLBACK_SNAPSHOT"

    # Revert to previous commit
    git checkout "$ROLLBACK_SNAPSHOT" 2>&1 | tee -a "$DEPLOY_LOG"

    # Redeploy
    log_info "Redeploying previous version..."
    railway up -d 2>&1 | tee -a "$DEPLOY_LOG"

    log_info "Waiting for rollback to complete..."
    sleep 30

    # Verify rollback
    if check_deployment_health; then
        log_info "✓ Rollback successful"
        send_notification "✅ Rollback Complete" "Successfully reverted to $ROLLBACK_SNAPSHOT" "success"
        return 0
    else
        log_error "Rollback health check failed"
        send_notification "❌ Rollback Failed" "Manual intervention required" "error"
        return 1
    fi
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    log_section "Railway 완전 자동화 배포 시작"
    log_info "Project: $PROJECT_NAME"
    log_info "Time: $(date)"
    log_info "Log: $DEPLOY_LOG"

    send_notification "🚀 Deployment Started" "Project: $PROJECT_NAME" "info"

    # Parse arguments
    parse_arguments "$@"

    # Pre-flight checks
    check_commands
    check_railway_auth
    check_railway_project
    check_git_status
    check_railway_env
    run_tests
    check_database_backup

    # Deployment
    if [ "$BLUE_GREEN_MODE" = true ]; then
        deploy_blue_green || {
            log_error "Blue-Green deployment failed"
            rollback
            exit 1
        }
    else
        deploy_standard || {
            log_error "Standard deployment failed"
            rollback
            exit 1
        }
    fi

    # Post-deployment verification
    if ! check_deployment_health; then
        log_error "Health check failed after deployment"
        rollback
        exit 1
    fi

    check_deployment_status
    check_deployment_metrics
    fetch_recent_logs

    # Success summary
    log_section "Deployment Complete"
    log_info "✓ Deployment successful"
    log_info "✓ Health checks passed"
    log_info "✓ Service is operational"

    local url=$(get_deployment_url)
    if [ -n "$url" ]; then
        log_info ""
        log_info "Deployment URL: $url"
        log_info "Health: $url/healthz"
        log_info "Status: $url/status"
        log_info "Metrics: $url/metrics"
    fi

    log_info ""
    log_info "Next steps:"
    log_info "1. Monitor logs: railway logs -f"
    log_info "2. Check metrics: curl $url/metrics"
    log_info "3. Review deployment log: $DEPLOY_LOG"

    send_notification "✅ Deployment Complete" "Service is operational at $url" "success"
}

# Error handler
trap 'log_error "Script failed at line $LINENO"; send_notification "❌ Deployment Failed" "Check logs: $DEPLOY_LOG" "error"; exit 1' ERR

# Run main
main "$@"
