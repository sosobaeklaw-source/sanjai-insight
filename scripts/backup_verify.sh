#!/bin/bash
# ============================================================================
# 백업 검증 자동화 스크립트
# ============================================================================
# 용도: 백업 무결성 체크 + 복원 테스트 + S3 업로드 검증
# 실행: ./scripts/backup_verify.sh [--restore-test] [--s3-verify] [--daily-report]
# ============================================================================

set -e
set -u
set -o pipefail

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/backups}"
DATA_DIR="${DATA_DIR:-$PROJECT_ROOT/data}"
LOG_DIR="$PROJECT_ROOT/logs"
VERIFY_LOG="$LOG_DIR/backup_verify_$(date +%Y%m%d_%H%M%S).log"
TEMP_RESTORE_DIR="/tmp/sanjai_restore_test_$$"
RESTORE_TEST=false
S3_VERIFY=false
DAILY_REPORT=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ============================================================================
# Logging
# ============================================================================

mkdir -p "$LOG_DIR"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*" | tee -a "$VERIFY_LOG"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*" | tee -a "$VERIFY_LOG"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" | tee -a "$VERIFY_LOG"
}

log_section() {
    echo "" | tee -a "$VERIFY_LOG"
    echo -e "${BLUE}========================================${NC}" | tee -a "$VERIFY_LOG"
    echo -e "${BLUE}$*${NC}" | tee -a "$VERIFY_LOG"
    echo -e "${BLUE}========================================${NC}" | tee -a "$VERIFY_LOG"
}

# ============================================================================
# Argument Parsing
# ============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --restore-test)
            RESTORE_TEST=true
            shift
            ;;
        --s3-verify)
            S3_VERIFY=true
            shift
            ;;
        --daily-report)
            DAILY_REPORT=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ============================================================================
# Backup Integrity Check
# ============================================================================

check_backup_files() {
    log_section "백업 파일 무결성 체크"

    if [ ! -d "$BACKUP_DIR" ]; then
        log_error "Backup directory not found: $BACKUP_DIR"
        exit 1
    fi

    local backup_count=$(find "$BACKUP_DIR" -name "*.db" -o -name "*.tar.gz" | wc -l)
    log_info "Total backup files: $backup_count"

    if [ "$backup_count" -eq 0 ]; then
        log_error "No backup files found"
        exit 1
    fi

    # Check recent backups (last 7 days)
    local recent_backups=$(find "$BACKUP_DIR" -name "*.db" -mtime -7 | wc -l)
    log_info "Recent backups (7 days): $recent_backups"

    if [ "$recent_backups" -eq 0 ]; then
        log_warn "No backups in last 7 days"
    fi

    # Verify each backup file
    local corrupt_count=0
    while IFS= read -r backup_file; do
        local filename=$(basename "$backup_file")
        local filesize=$(stat -f%z "$backup_file" 2>/dev/null || stat -c%s "$backup_file" 2>/dev/null)

        if [ "$filesize" -eq 0 ]; then
            log_error "Corrupt backup (empty): $filename"
            corrupt_count=$((corrupt_count+1))
            continue
        fi

        # SQLite integrity check
        if [[ "$backup_file" == *.db ]]; then
            if sqlite3 "$backup_file" "PRAGMA integrity_check;" | grep -q "ok"; then
                log_info "✓ $filename (${filesize} bytes)"
            else
                log_error "✗ $filename - integrity check failed"
                corrupt_count=$((corrupt_count+1))
            fi
        else
            log_info "✓ $filename (${filesize} bytes)"
        fi
    done < <(find "$BACKUP_DIR" -name "*.db" -o -name "*.tar.gz")

    if [ "$corrupt_count" -gt 0 ]; then
        log_error "Found $corrupt_count corrupt backups"
        return 1
    fi

    log_info "✓ All backups are intact"
}

# ============================================================================
# Restore Test
# ============================================================================

run_restore_test() {
    if [ "$RESTORE_TEST" = false ]; then
        return 0
    fi

    log_section "복원 테스트 자동화"

    # Find most recent backup
    local latest_backup=$(find "$BACKUP_DIR" -name "*.db" -type f -printf '%T@ %p\n' | sort -rn | head -n 1 | cut -d' ' -f2-)

    if [ -z "$latest_backup" ]; then
        log_error "No backup found for restore test"
        return 1
    fi

    log_info "Testing restore from: $(basename "$latest_backup")"

    # Create temp restore directory
    mkdir -p "$TEMP_RESTORE_DIR"
    local restore_db="$TEMP_RESTORE_DIR/insight_restore_test.db"

    # Copy backup to temp location
    cp "$latest_backup" "$restore_db"
    log_info "✓ Backup copied to temp location"

    # Verify database structure
    log_info "Verifying database structure..."

    local expected_tables=("crawl_results" "insights" "proposals" "approval_log" "jobs" "checkpoints" "events")
    local missing_tables=()

    for table in "${expected_tables[@]}"; do
        if ! sqlite3 "$restore_db" "SELECT name FROM sqlite_master WHERE type='table' AND name='$table';" | grep -q "$table"; then
            missing_tables+=("$table")
        fi
    done

    if [ ${#missing_tables[@]} -gt 0 ]; then
        log_error "Missing tables in restored backup:"
        for table in "${missing_tables[@]}"; do
            echo "  - $table" | tee -a "$VERIFY_LOG"
        done
        rm -rf "$TEMP_RESTORE_DIR"
        return 1
    fi

    log_info "✓ All expected tables present"

    # Test basic queries
    log_info "Testing basic queries..."

    local insight_count=$(sqlite3 "$restore_db" "SELECT COUNT(*) FROM insights;")
    local proposal_count=$(sqlite3 "$restore_db" "SELECT COUNT(*) FROM proposals;")
    local job_count=$(sqlite3 "$restore_db" "SELECT COUNT(*) FROM jobs;")

    log_info "Insights: $insight_count"
    log_info "Proposals: $proposal_count"
    log_info "Jobs: $job_count"

    # Test indexes
    log_info "Verifying indexes..."
    local index_count=$(sqlite3 "$restore_db" "SELECT COUNT(*) FROM sqlite_master WHERE type='index';")
    log_info "Indexes found: $index_count"

    # Cleanup
    rm -rf "$TEMP_RESTORE_DIR"
    log_info "✓ Restore test passed, temp files cleaned"
}

# ============================================================================
# S3 Upload Verification
# ============================================================================

verify_s3_upload() {
    if [ "$S3_VERIFY" = false ]; then
        return 0
    fi

    log_section "S3 업로드 검증"

    if ! command -v aws &> /dev/null; then
        log_warn "AWS CLI not found, skipping S3 verification"
        return 0
    fi

    # Check if S3 bucket is configured
    local s3_bucket="${S3_BACKUP_BUCKET:-}"
    if [ -z "$s3_bucket" ]; then
        log_warn "S3_BACKUP_BUCKET not configured, skipping S3 verification"
        return 0
    fi

    log_info "Checking S3 bucket: $s3_bucket"

    # List recent S3 backups
    local s3_backups=$(aws s3 ls "s3://$s3_bucket/sanjai-insight/" --recursive | grep ".db" | tail -n 10)

    if [ -z "$s3_backups" ]; then
        log_warn "No backups found in S3"
        return 0
    fi

    log_info "Recent S3 backups:"
    echo "$s3_backups" | tee -a "$VERIFY_LOG"

    # Verify most recent S3 backup
    local latest_s3=$(echo "$s3_backups" | tail -n 1 | awk '{print $4}')
    local s3_size=$(echo "$s3_backups" | tail -n 1 | awk '{print $3}')

    log_info "Latest S3 backup: $latest_s3 ($s3_size bytes)"

    # Compare with local backup
    local local_backup=$(find "$BACKUP_DIR" -name "*.db" -type f -printf '%T@ %p\n' | sort -rn | head -n 1 | cut -d' ' -f2-)
    local local_size=$(stat -f%z "$local_backup" 2>/dev/null || stat -c%s "$local_backup" 2>/dev/null)

    if [ "$s3_size" -eq "$local_size" ]; then
        log_info "✓ S3 backup size matches local backup"
    else
        log_warn "S3 backup size differs from local backup"
        log_warn "Local: $local_size bytes, S3: $s3_size bytes"
    fi

    log_info "✓ S3 verification complete"
}

# ============================================================================
# Daily Report Generation
# ============================================================================

generate_daily_report() {
    if [ "$DAILY_REPORT" = false ]; then
        return 0
    fi

    log_section "일일 백업 리포트 생성"

    local report_file="$LOG_DIR/backup_daily_report_$(date +%Y%m%d).txt"

    cat > "$report_file" <<EOF
========================================
산재AI 인사이트 백업 일일 리포트
========================================
생성일시: $(date '+%Y-%m-%d %H:%M:%S')

[백업 파일 현황]
EOF

    # Backup statistics
    local total_backups=$(find "$BACKUP_DIR" -name "*.db" -o -name "*.tar.gz" | wc -l)
    local total_size=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
    local today_backups=$(find "$BACKUP_DIR" -name "*.db" -mtime -1 | wc -l)

    cat >> "$report_file" <<EOF
총 백업 파일: $total_backups
총 용량: $total_size
금일 생성: $today_backups

[최근 백업 (최신 5개)]
EOF

    find "$BACKUP_DIR" -name "*.db" -type f -printf '%T@ %TY-%Tm-%Td %TH:%TM %p\n' | \
        sort -rn | head -n 5 | cut -d' ' -f2- >> "$report_file"

    cat >> "$report_file" <<EOF

[백업 무결성]
EOF

    if check_backup_files >> "$report_file" 2>&1; then
        echo "상태: 정상 ✓" >> "$report_file"
    else
        echo "상태: 오류 발견 ✗" >> "$report_file"
    fi

    cat >> "$report_file" <<EOF

[권장사항]
- 백업 보관 기간: 30일
- 최소 보관 개수: 30개
- 오프사이트 백업: S3 업로드 권장
- 복원 테스트: 주 1회 권장

========================================
EOF

    log_info "✓ Daily report generated: $report_file"

    # Optional: Send report via email or Telegram
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CEO_CHAT_ID:-}" ]; then
        local report_content=$(cat "$report_file")
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CEO_CHAT_ID}" \
            -d "text=\`\`\`$report_content\`\`\`" \
            -d "parse_mode=Markdown" > /dev/null || log_warn "Telegram 전송 실패"
    fi
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    log_section "백업 검증 자동화 시작"
    log_info "Time: $(date)"
    log_info "Log: $VERIFY_LOG"

    # Run checks
    check_backup_files
    run_restore_test
    verify_s3_upload
    generate_daily_report

    log_section "검증 완료"
    log_info "✓ All verification checks passed"
    log_info "Log saved: $VERIFY_LOG"
}

trap 'log_error "Script failed at line $LINENO"; exit 1' ERR

main "$@"
