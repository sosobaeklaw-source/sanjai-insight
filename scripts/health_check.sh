#!/bin/bash
# ============================================================================
# Health Check Script for sanjai-insight
# ============================================================================
# 용도: 배포 후 시스템 상태 확인
# 실행: ./scripts/health_check.sh [URL]
# 예시: ./scripts/health_check.sh https://sanjai-insight.up.railway.app
# ============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
BASE_URL="${1:-http://localhost:8000}"
TIMEOUT=10

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

check_endpoint() {
    local endpoint="$1"
    local expected_status="$2"
    local url="${BASE_URL}${endpoint}"

    log_info "Checking ${endpoint}..."

    response=$(curl -s -w "\n%{http_code}" --max-time "$TIMEOUT" "$url" || echo "FAILED")

    if [[ "$response" == "FAILED" ]]; then
        log_error "${endpoint} - Connection failed"
        return 1
    fi

    status_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [[ "$status_code" == "$expected_status" ]]; then
        log_info "${endpoint} - OK (${status_code})"
        return 0
    else
        log_error "${endpoint} - Expected ${expected_status}, got ${status_code}"
        echo "$body"
        return 1
    fi
}

# ============================================================================
# Health Checks
# ============================================================================

log_info "Starting health checks for: $BASE_URL"
echo ""

# Check if curl is available
if ! command -v curl &> /dev/null; then
    log_error "curl command not found. Please install curl."
    exit 1
fi

# Check if jq is available (optional but recommended)
if ! command -v jq &> /dev/null; then
    log_warn "jq not found. JSON output will not be formatted."
    JQ_AVAILABLE=false
else
    JQ_AVAILABLE=true
fi

echo ""
log_info "========================================="
log_info "Basic Health Checks"
log_info "========================================="
echo ""

# 1. Liveness check
if check_endpoint "/healthz" "200"; then
    HEALTHZ_OK=true
else
    HEALTHZ_OK=false
fi
echo ""

# 2. Detailed health check
log_info "Checking /health..."
health_response=$(curl -s --max-time "$TIMEOUT" "${BASE_URL}/health" || echo "FAILED")

if [[ "$health_response" == "FAILED" ]]; then
    log_error "/health - Connection failed"
    HEALTH_OK=false
else
    log_info "/health - OK"
    if [[ "$JQ_AVAILABLE" == true ]]; then
        echo "$health_response" | jq '.'
    else
        echo "$health_response"
    fi
    HEALTH_OK=true
fi
echo ""

# 3. Metrics check
if check_endpoint "/metrics" "200"; then
    METRICS_OK=true
else
    METRICS_OK=false
fi
echo ""

# ============================================================================
# Detailed Checks
# ============================================================================

if [[ "$HEALTH_OK" == true ]]; then
    log_info "========================================="
    log_info "Detailed Status"
    log_info "========================================="
    echo ""

    # Parse health response
    if [[ "$JQ_AVAILABLE" == true ]]; then
        db_connected=$(echo "$health_response" | jq -r '.db_connected')
        telegram_configured=$(echo "$health_response" | jq -r '.telegram_configured')
        vault_accessible=$(echo "$health_response" | jq -r '.vault_accessible')
        pending_jobs=$(echo "$health_response" | jq -r '.pending_jobs')
        running_jobs=$(echo "$health_response" | jq -r '.running_jobs')
        insights_24h=$(echo "$health_response" | jq -r '.insights_24h')
        cost_24h_usd=$(echo "$health_response" | jq -r '.cost_24h_usd')

        log_info "Database Connected: $db_connected"
        log_info "Telegram Configured: $telegram_configured"
        log_info "Vault Accessible: $vault_accessible"
        log_info "Pending Jobs: $pending_jobs"
        log_info "Running Jobs: $running_jobs"
        log_info "Insights (24h): $insights_24h"
        log_info "Cost (24h): \$${cost_24h_usd}"
    fi
    echo ""
fi

# ============================================================================
# Summary
# ============================================================================

log_info "========================================="
log_info "Health Check Summary"
log_info "========================================="
echo ""

total_checks=3
passed_checks=0

if [[ "$HEALTHZ_OK" == true ]]; then
    log_info "[✓] Liveness check"
    ((passed_checks++))
else
    log_error "[✗] Liveness check"
fi

if [[ "$HEALTH_OK" == true ]]; then
    log_info "[✓] Health check"
    ((passed_checks++))
else
    log_error "[✗] Health check"
fi

if [[ "$METRICS_OK" == true ]]; then
    log_info "[✓] Metrics endpoint"
    ((passed_checks++))
else
    log_error "[✗] Metrics endpoint"
fi

echo ""
log_info "Passed: ${passed_checks}/${total_checks}"

if [[ $passed_checks -eq $total_checks ]]; then
    log_info "All checks passed!"
    exit 0
else
    log_error "Some checks failed. Please investigate."
    exit 1
fi
