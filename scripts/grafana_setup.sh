#!/bin/bash
# ============================================================================
# Grafana 자동 설정 스크립트
# ============================================================================
# 용도: Grafana 대시보드 + Data Source + Alert 자동 구성
# 실행: ./scripts/grafana_setup.sh --api-key YOUR_KEY --url http://grafana:3000
# ============================================================================

set -e
set -u
set -o pipefail

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
GRAFANA_API_KEY="${GRAFANA_API_KEY:-}"
DATASOURCE_URL="${DATASOURCE_URL:-http://sanjai-insight:8000/metrics}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ============================================================================
# Logging
# ============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

log_section() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$*${NC}"
    echo -e "${BLUE}========================================${NC}"
}

# ============================================================================
# Argument Parsing
# ============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --api-key)
            GRAFANA_API_KEY="$2"
            shift 2
            ;;
        --url)
            GRAFANA_URL="$2"
            shift 2
            ;;
        --datasource-url)
            DATASOURCE_URL="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ============================================================================
# Pre-flight Checks
# ============================================================================

check_prerequisites() {
    log_section "Pre-flight Checks"

    if [ -z "$GRAFANA_API_KEY" ]; then
        log_error "Grafana API key required. Use --api-key option."
        log_info "Generate API key: Grafana UI → Configuration → API Keys"
        exit 1
    fi

    if ! command -v curl &> /dev/null; then
        log_error "curl command not found"
        exit 1
    fi

    log_info "✓ Prerequisites OK"
}

test_grafana_connection() {
    log_section "Testing Grafana Connection"

    local response=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $GRAFANA_API_KEY" "$GRAFANA_URL/api/health")
    local body=$(echo "$response" | head -n -1)
    local status=$(echo "$response" | tail -n 1)

    if [ "$status" -eq 200 ]; then
        log_info "✓ Grafana connection OK"
        log_info "Response: $body"
    else
        log_error "Grafana connection failed (HTTP $status)"
        log_error "Response: $body"
        exit 1
    fi
}

# ============================================================================
# Data Source Setup
# ============================================================================

create_prometheus_datasource() {
    log_section "Creating Prometheus Data Source"

    local datasource_payload=$(cat <<EOF
{
  "name": "SanjaiInsight-Prometheus",
  "type": "prometheus",
  "url": "$DATASOURCE_URL",
  "access": "proxy",
  "isDefault": true,
  "jsonData": {
    "httpMethod": "POST",
    "timeInterval": "30s"
  }
}
EOF
)

    local response=$(curl -s -w "\n%{http_code}" -X POST \
        -H "Authorization: Bearer $GRAFANA_API_KEY" \
        -H "Content-Type: application/json" \
        -d "$datasource_payload" \
        "$GRAFANA_URL/api/datasources")

    local body=$(echo "$response" | head -n -1)
    local status=$(echo "$response" | tail -n 1)

    if [ "$status" -eq 200 ] || [ "$status" -eq 409 ]; then
        log_info "✓ Data source created/updated"
    else
        log_error "Failed to create data source (HTTP $status)"
        log_error "Response: $body"
        return 1
    fi
}

# ============================================================================
# Dashboard Import
# ============================================================================

import_dashboard() {
    log_section "Importing Dashboard"

    local dashboard_file="$PROJECT_ROOT/config/grafana_dashboard.json"

    if [ ! -f "$dashboard_file" ]; then
        log_warn "Dashboard file not found: $dashboard_file"
        log_info "Creating default dashboard..."
        create_default_dashboard
        return
    fi

    local dashboard_json=$(cat "$dashboard_file")

    # Wrap dashboard JSON in import payload
    local import_payload=$(cat <<EOF
{
  "dashboard": $dashboard_json,
  "overwrite": true,
  "inputs": [
    {
      "name": "DS_PROMETHEUS",
      "type": "datasource",
      "pluginId": "prometheus",
      "value": "SanjaiInsight-Prometheus"
    }
  ]
}
EOF
)

    local response=$(curl -s -w "\n%{http_code}" -X POST \
        -H "Authorization: Bearer $GRAFANA_API_KEY" \
        -H "Content-Type: application/json" \
        -d "$import_payload" \
        "$GRAFANA_URL/api/dashboards/import")

    local body=$(echo "$response" | head -n -1)
    local status=$(echo "$response" | tail -n 1)

    if [ "$status" -eq 200 ]; then
        log_info "✓ Dashboard imported successfully"
        local dashboard_url=$(echo "$body" | grep -o '"url":"[^"]*"' | cut -d'"' -f4)
        log_info "Dashboard URL: $GRAFANA_URL$dashboard_url"
    else
        log_error "Failed to import dashboard (HTTP $status)"
        log_error "Response: $body"
        return 1
    fi
}

create_default_dashboard() {
    log_info "Creating minimal default dashboard..."

    local default_dashboard=$(cat <<'EOF'
{
  "dashboard": {
    "title": "SanjaiInsight Monitoring",
    "tags": ["sanjai", "insight"],
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "System Health",
        "type": "stat",
        "targets": [
          {
            "expr": "up{job=\"sanjai-insight\"}",
            "refId": "A"
          }
        ],
        "gridPos": {
          "h": 8,
          "w": 12,
          "x": 0,
          "y": 0
        }
      },
      {
        "id": 2,
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(http_requests_total[5m])",
            "refId": "A"
          }
        ],
        "gridPos": {
          "h": 8,
          "w": 12,
          "x": 12,
          "y": 0
        }
      }
    ]
  },
  "overwrite": true
}
EOF
)

    local response=$(curl -s -w "\n%{http_code}" -X POST \
        -H "Authorization: Bearer $GRAFANA_API_KEY" \
        -H "Content-Type: application/json" \
        -d "$default_dashboard" \
        "$GRAFANA_URL/api/dashboards/db")

    local body=$(echo "$response" | head -n -1)
    local status=$(echo "$response" | tail -n 1)

    if [ "$status" -eq 200 ]; then
        log_info "✓ Default dashboard created"
    else
        log_warn "Failed to create default dashboard (HTTP $status)"
    fi
}

# ============================================================================
# Alert Configuration
# ============================================================================

create_alert_contact_point() {
    log_section "Creating Alert Contact Point"

    # Telegram contact point
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CEO_CHAT_ID:-}" ]; then
        local contact_point=$(cat <<EOF
{
  "name": "Telegram-CEO",
  "type": "telegram",
  "settings": {
    "bottoken": "$TELEGRAM_BOT_TOKEN",
    "chatid": "$TELEGRAM_CEO_CHAT_ID"
  }
}
EOF
)

        local response=$(curl -s -w "\n%{http_code}" -X POST \
            -H "Authorization: Bearer $GRAFANA_API_KEY" \
            -H "Content-Type: application/json" \
            -d "$contact_point" \
            "$GRAFANA_URL/api/v1/provisioning/contact-points")

        local body=$(echo "$response" | head -n -1)
        local status=$(echo "$response" | tail -n 1)

        if [ "$status" -eq 200 ] || [ "$status" -eq 202 ]; then
            log_info "✓ Telegram contact point created"
        else
            log_warn "Failed to create contact point (HTTP $status)"
        fi
    else
        log_warn "Telegram credentials not configured, skipping contact point"
    fi
}

create_alert_rules() {
    log_section "Creating Alert Rules"

    # High error rate alert
    local alert_rule=$(cat <<'EOF'
{
  "title": "High Error Rate",
  "condition": "A",
  "data": [
    {
      "refId": "A",
      "queryType": "",
      "relativeTimeRange": {
        "from": 600,
        "to": 0
      },
      "datasourceUid": "prometheus",
      "model": {
        "expr": "rate(http_requests_total{status=~\"5..\"}[5m]) > 0.1",
        "refId": "A"
      }
    }
  ],
  "noDataState": "NoData",
  "execErrState": "Alerting",
  "for": "5m",
  "annotations": {
    "description": "Error rate is above 10% for 5 minutes",
    "summary": "High error rate detected"
  },
  "labels": {
    "severity": "critical"
  }
}
EOF
)

    log_info "Alert rule creation requires Grafana 9.0+ provisioning API"
    log_info "Please configure alerts manually in Grafana UI or via provisioning files"
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    log_section "Grafana 자동 설정 시작"

    check_prerequisites
    test_grafana_connection
    create_prometheus_datasource
    import_dashboard
    create_alert_contact_point
    create_alert_rules

    log_section "설정 완료"
    log_info "✓ Grafana setup complete"
    log_info ""
    log_info "Next steps:"
    log_info "1. Access Grafana: $GRAFANA_URL"
    log_info "2. Check dashboards: $GRAFANA_URL/dashboards"
    log_info "3. Configure additional alerts as needed"
}

trap 'log_error "Script failed at line $LINENO"; exit 1' ERR

main "$@"
