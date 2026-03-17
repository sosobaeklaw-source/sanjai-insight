#!/usr/bin/env bash
# SQLite Backup Script for sanjai-insight
# Supports Railway volume and S3 backup

set -euo pipefail

# Configuration
DB_PATH="${DB_PATH:-./data/sanjai.db}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-sanjai-insight-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

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

# Check if database exists
if [ ! -f "$DB_PATH" ]; then
    error "Database not found at $DB_PATH"
fi

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Generate backup filename with timestamp
TIMESTAMP=$(date +'%Y%m%d_%H%M%S')
BACKUP_FILENAME="sanjai_backup_${TIMESTAMP}.db"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILENAME}"

log "Starting backup: $DB_PATH -> $BACKUP_PATH"

# Create backup using SQLite backup API (hot backup)
if command -v sqlite3 &> /dev/null; then
    log "Using sqlite3 backup command..."
    sqlite3 "$DB_PATH" ".backup '$BACKUP_PATH'"
else
    # Fallback to simple copy (requires DB to be idle)
    warn "sqlite3 not found, using cp (not recommended for active DB)"
    cp "$DB_PATH" "$BACKUP_PATH"
fi

# Verify backup
if [ ! -f "$BACKUP_PATH" ]; then
    error "Backup failed: file not created"
fi

BACKUP_SIZE=$(du -h "$BACKUP_PATH" | cut -f1)
log "Backup created: $BACKUP_PATH ($BACKUP_SIZE)"

# Compress backup
log "Compressing backup..."
gzip -f "$BACKUP_PATH"
COMPRESSED_PATH="${BACKUP_PATH}.gz"

if [ -f "$COMPRESSED_PATH" ]; then
    COMPRESSED_SIZE=$(du -h "$COMPRESSED_PATH" | cut -f1)
    log "Backup compressed: $COMPRESSED_PATH ($COMPRESSED_SIZE)"
else
    error "Compression failed"
fi

# Upload to S3 if configured
if [ -n "$S3_BUCKET" ]; then
    log "Uploading to S3: s3://${S3_BUCKET}/${S3_PREFIX}/"

    if command -v aws &> /dev/null; then
        aws s3 cp "$COMPRESSED_PATH" "s3://${S3_BUCKET}/${S3_PREFIX}/${BACKUP_FILENAME}.gz" \
            --no-progress

        if [ $? -eq 0 ]; then
            log "S3 upload successful"
        else
            warn "S3 upload failed"
        fi
    else
        warn "AWS CLI not found, skipping S3 upload"
    fi
fi

# Cleanup old backups (local)
log "Cleaning up old backups (retention: ${RETENTION_DAYS} days)..."
find "$BACKUP_DIR" -name "sanjai_backup_*.db.gz" -type f -mtime +${RETENTION_DAYS} -delete

REMAINING=$(find "$BACKUP_DIR" -name "sanjai_backup_*.db.gz" -type f | wc -l)
log "Local backups remaining: $REMAINING"

# Cleanup old S3 backups if configured
if [ -n "$S3_BUCKET" ] && command -v aws &> /dev/null; then
    log "Cleaning up old S3 backups..."

    CUTOFF_DATE=$(date -d "${RETENTION_DAYS} days ago" +'%Y-%m-%d' 2>/dev/null || \
                  date -v-${RETENTION_DAYS}d +'%Y-%m-%d' 2>/dev/null || \
                  echo "")

    if [ -n "$CUTOFF_DATE" ]; then
        aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" | \
        awk '{print $4}' | \
        while read -r file; do
            FILE_DATE=$(echo "$file" | grep -oP '\d{8}' | head -1)
            if [ -n "$FILE_DATE" ]; then
                FILE_DATE_FORMATTED="${FILE_DATE:0:4}-${FILE_DATE:4:2}-${FILE_DATE:6:2}"
                if [[ "$FILE_DATE_FORMATTED" < "$CUTOFF_DATE" ]]; then
                    log "Deleting old S3 backup: $file"
                    aws s3 rm "s3://${S3_BUCKET}/${S3_PREFIX}/${file}"
                fi
            fi
        done
    fi
fi

log "Backup complete: $COMPRESSED_PATH"

# Optional: Verify integrity
if command -v sqlite3 &> /dev/null; then
    log "Verifying backup integrity..."
    gunzip -c "$COMPRESSED_PATH" > /tmp/verify_backup.db

    INTEGRITY_CHECK=$(sqlite3 /tmp/verify_backup.db "PRAGMA integrity_check;" 2>&1)

    if [ "$INTEGRITY_CHECK" = "ok" ]; then
        log "✓ Backup integrity verified"
    else
        error "✗ Backup integrity check failed: $INTEGRITY_CHECK"
    fi

    rm -f /tmp/verify_backup.db
fi

log "All backup operations completed successfully"
