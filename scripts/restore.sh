#!/usr/bin/env bash
# SQLite Restore Script for sanjai-insight
# Restores from local or S3 backup

set -euo pipefail

# Configuration
DB_PATH="${DB_PATH:-./data/sanjai.db}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-sanjai-insight-backups}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
    exit 1
}

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -f, --file FILE       Restore from specific backup file"
    echo "  -l, --latest          Restore from latest local backup"
    echo "  -s, --s3-latest       Restore from latest S3 backup"
    echo "  -d, --date DATE       Restore from backup on DATE (YYYYMMDD)"
    echo "  -y, --yes             Skip confirmation prompt"
    echo "  -h, --help            Show this help message"
    echo ""
    exit 0
}

# Parse arguments
BACKUP_FILE=""
USE_LATEST=false
USE_S3_LATEST=false
BACKUP_DATE=""
SKIP_CONFIRM=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--file)
            BACKUP_FILE="$2"
            shift 2
            ;;
        -l|--latest)
            USE_LATEST=true
            shift
            ;;
        -s|--s3-latest)
            USE_S3_LATEST=true
            shift
            ;;
        -d|--date)
            BACKUP_DATE="$2"
            shift 2
            ;;
        -y|--yes)
            SKIP_CONFIRM=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

# Determine backup file
if [ -n "$BACKUP_FILE" ]; then
    if [ ! -f "$BACKUP_FILE" ]; then
        error "Backup file not found: $BACKUP_FILE"
    fi
elif $USE_LATEST; then
    log "Finding latest local backup..."
    BACKUP_FILE=$(find "$BACKUP_DIR" -name "sanjai_backup_*.db.gz" -type f | sort -r | head -1)

    if [ -z "$BACKUP_FILE" ]; then
        error "No local backups found in $BACKUP_DIR"
    fi
elif $USE_S3_LATEST; then
    if [ -z "$S3_BUCKET" ]; then
        error "S3_BUCKET not configured"
    fi

    if ! command -v aws &> /dev/null; then
        error "AWS CLI not found"
    fi

    log "Finding latest S3 backup..."
    LATEST_S3_FILE=$(aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" | \
                     grep "sanjai_backup_.*\.db\.gz" | \
                     sort -r | \
                     head -1 | \
                     awk '{print $4}')

    if [ -z "$LATEST_S3_FILE" ]; then
        error "No S3 backups found"
    fi

    log "Downloading from S3: $LATEST_S3_FILE"
    BACKUP_FILE="/tmp/${LATEST_S3_FILE}"
    aws s3 cp "s3://${S3_BUCKET}/${S3_PREFIX}/${LATEST_S3_FILE}" "$BACKUP_FILE" --no-progress

elif [ -n "$BACKUP_DATE" ]; then
    log "Finding backup for date: $BACKUP_DATE"
    BACKUP_FILE=$(find "$BACKUP_DIR" -name "sanjai_backup_${BACKUP_DATE}_*.db.gz" -type f | sort -r | head -1)

    if [ -z "$BACKUP_FILE" ]; then
        # Try S3
        if [ -n "$S3_BUCKET" ] && command -v aws &> /dev/null; then
            log "Not found locally, checking S3..."
            LATEST_S3_FILE=$(aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" | \
                             grep "sanjai_backup_${BACKUP_DATE}_.*\.db\.gz" | \
                             sort -r | \
                             head -1 | \
                             awk '{print $4}')

            if [ -n "$LATEST_S3_FILE" ]; then
                log "Downloading from S3: $LATEST_S3_FILE"
                BACKUP_FILE="/tmp/${LATEST_S3_FILE}"
                aws s3 cp "s3://${S3_BUCKET}/${S3_PREFIX}/${LATEST_S3_FILE}" "$BACKUP_FILE" --no-progress
            else
                error "No backup found for date: $BACKUP_DATE"
            fi
        else
            error "No backup found for date: $BACKUP_DATE"
        fi
    fi
else
    error "No restore option specified. Use -h for help."
fi

log "Backup file: $BACKUP_FILE"
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
log "Backup size: $BACKUP_SIZE"

# Confirmation
if ! $SKIP_CONFIRM; then
    warn "This will REPLACE the current database at: $DB_PATH"
    read -p "Continue? (yes/no): " CONFIRM

    if [ "$CONFIRM" != "yes" ]; then
        log "Restore cancelled"
        exit 0
    fi
fi

# Create database directory if needed
mkdir -p "$(dirname "$DB_PATH")"

# Backup current database
if [ -f "$DB_PATH" ]; then
    CURRENT_BACKUP="${DB_PATH}.before_restore.$(date +'%Y%m%d_%H%M%S')"
    log "Backing up current database to: $CURRENT_BACKUP"
    cp "$DB_PATH" "$CURRENT_BACKUP"
fi

# Decompress and restore
log "Decompressing backup..."
TEMP_DB="/tmp/restore_temp_$(date +'%Y%m%d_%H%M%S').db"
gunzip -c "$BACKUP_FILE" > "$TEMP_DB"

if [ ! -f "$TEMP_DB" ]; then
    error "Decompression failed"
fi

# Verify integrity
if command -v sqlite3 &> /dev/null; then
    log "Verifying backup integrity..."
    INTEGRITY_CHECK=$(sqlite3 "$TEMP_DB" "PRAGMA integrity_check;" 2>&1)

    if [ "$INTEGRITY_CHECK" != "ok" ]; then
        error "Backup integrity check failed: $INTEGRITY_CHECK"
    fi

    log "✓ Backup integrity verified"
fi

# Move to final location
log "Restoring database..."
mv "$TEMP_DB" "$DB_PATH"

if [ -f "$DB_PATH" ]; then
    log "✓ Database restored successfully"
else
    error "Restore failed"
fi

# Cleanup
if [[ "$BACKUP_FILE" == /tmp/* ]]; then
    rm -f "$BACKUP_FILE"
fi

# Final verification
if command -v sqlite3 &> /dev/null; then
    log "Final verification..."

    ROW_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>&1)

    if [[ "$ROW_COUNT" =~ ^[0-9]+$ ]]; then
        log "✓ Database contains $ROW_COUNT tables"
    else
        error "Final verification failed"
    fi
fi

log "Restore complete: $DB_PATH"
log "NOTE: Restart the application to use the restored database"
