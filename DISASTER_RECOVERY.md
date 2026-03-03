# Disaster Recovery Procedures
## sanjai-insight System Recovery Guide

> **Last Updated:** 2026-03-03
> **Owner:** Operations Team
> **Review Frequency:** Quarterly

---

## Table of Contents

1. [Overview](#overview)
2. [Backup Strategy](#backup-strategy)
3. [Recovery Scenarios](#recovery-scenarios)
4. [Step-by-Step Procedures](#step-by-step-procedures)
5. [Verification & Testing](#verification--testing)
6. [Contact Information](#contact-information)

---

## Overview

### Purpose

This document defines disaster recovery procedures for the sanjai-insight system, ensuring business continuity in case of data loss, system failures, or catastrophic events.

### Recovery Objectives

| Metric | Target | Notes |
|--------|--------|-------|
| **RTO** (Recovery Time Objective) | 2 hours | Maximum acceptable downtime |
| **RPO** (Recovery Point Objective) | 24 hours | Maximum acceptable data loss |
| **Data Integrity** | 100% | Zero tolerance for data corruption |

### Backup Schedule

- **Frequency:** Every 24 hours (automated)
- **Retention:** 30 days (local + S3)
- **Verification:** Daily integrity checks
- **Monitoring:** Alert if backup fails

---

## Backup Strategy

### Backup Types

#### 1. Automated Daily Backups

- **What:** Full SQLite database dump
- **When:** 03:00 UTC daily
- **Where:** Local volume + S3
- **Format:** Compressed (gzip)

```bash
# Triggered automatically by BackupManager
# Manual trigger:
bash scripts/backup.sh
```

#### 2. Pre-Deployment Backups

- **What:** Full snapshot before deployments
- **When:** Immediately before `railway up`
- **Where:** S3 with `pre-deploy` tag
- **Format:** Compressed + tagged

```bash
# Before deployment:
S3_PREFIX="sanjai-insight-pre-deploy" bash scripts/backup.sh
```

#### 3. On-Demand Backups

- **What:** Manual snapshots for testing/migrations
- **When:** As needed
- **Where:** Local or S3

```bash
# Manual backup:
DB_PATH=./data/sanjai.db bash scripts/backup.sh
```

### Backup Verification

All backups are automatically verified for:

1. **Integrity:** `PRAGMA integrity_check`
2. **Completeness:** Table count validation
3. **Accessibility:** Decompression test

---

## Recovery Scenarios

### Scenario 1: Data Corruption (Database Integrity Failure)

**Symptoms:**
- SQLite errors: "database disk image is malformed"
- Application crashes on DB access
- Integrity check failures

**Impact:** HIGH
**RTO:** 30 minutes
**RPO:** 24 hours

**Procedure:** [See Section 4.1](#41-data-corruption-recovery)

---

### Scenario 2: Accidental Data Deletion

**Symptoms:**
- Missing tables or records
- User reports data loss
- Audit logs show unexpected deletions

**Impact:** MEDIUM
**RTO:** 1 hour
**RPO:** 24 hours

**Procedure:** [See Section 4.2](#42-accidental-deletion-recovery)

---

### Scenario 3: Railway Volume Loss

**Symptoms:**
- Railway service restart with empty volume
- Database file not found errors
- Fresh schema initialization

**Impact:** CRITICAL
**RTO:** 2 hours
**RPO:** 24 hours

**Procedure:** [See Section 4.3](#43-volume-loss-recovery)

---

### Scenario 4: Complete System Failure

**Symptoms:**
- Railway service deleted
- All infrastructure lost
- Need to rebuild from scratch

**Impact:** CRITICAL
**RTO:** 4 hours
**RPO:** 24 hours

**Procedure:** [See Section 4.4](#44-complete-system-rebuild)

---

## Step-by-Step Procedures

### 4.1 Data Corruption Recovery

**Prerequisites:**
- SSH/shell access to Railway service
- Latest backup available

**Steps:**

1. **Verify Corruption**

```bash
sqlite3 /data/sanjai.db "PRAGMA integrity_check;"
# If output != "ok", proceed with recovery
```

2. **Stop Application**

```bash
railway run -- killall python3
# Or use Railway dashboard to restart service
```

3. **Backup Corrupted DB (for forensics)**

```bash
cp /data/sanjai.db /data/sanjai.db.corrupted.$(date +%Y%m%d_%H%M%S)
```

4. **Restore from Latest Backup**

```bash
cd /app
bash scripts/restore.sh --s3-latest --yes
```

5. **Verify Restoration**

```bash
sqlite3 /data/sanjai.db "PRAGMA integrity_check;"
sqlite3 /data/sanjai.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table';"
```

6. **Restart Application**

```bash
railway restart
```

7. **Verify Functionality**

```bash
curl http://localhost:8000/health
# Check Telegram bot responds to /status
```

**Rollback:** If restore fails, try previous backup:

```bash
bash scripts/restore.sh --date YYYYMMDD --yes
```

---

### 4.2 Accidental Deletion Recovery

**Prerequisites:**
- Identify deletion timestamp
- Backup exists before deletion

**Steps:**

1. **Identify Last Good Backup**

```bash
# List backups
ls -lh backups/
# Or S3:
aws s3 ls s3://YOUR_BUCKET/sanjai-insight-backups/
```

2. **Restore to Temporary Location**

```bash
# Download and extract backup
DB_PATH=/tmp/recovery.db bash scripts/restore.sh --date YYYYMMDD --yes
```

3. **Extract Missing Data**

```bash
# Query deleted data from restored backup
sqlite3 /tmp/recovery.db "SELECT * FROM your_table WHERE condition;"

# Export to CSV
sqlite3 /tmp/recovery.db <<EOF
.mode csv
.output /tmp/recovered_data.csv
SELECT * FROM your_table WHERE condition;
EOF
```

4. **Import to Production DB**

```bash
# Import recovered data
sqlite3 /data/sanjai.db <<EOF
.mode csv
.import /tmp/recovered_data.csv your_table
EOF
```

5. **Verify Recovery**

```bash
sqlite3 /data/sanjai.db "SELECT COUNT(*) FROM your_table WHERE condition;"
```

6. **Cleanup**

```bash
rm -f /tmp/recovery.db /tmp/recovered_data.csv
```

---

### 4.3 Volume Loss Recovery

**Prerequisites:**
- Railway CLI installed
- S3 backups available
- Environment variables backed up

**Steps:**

1. **Confirm Volume Loss**

```bash
railway run -- ls -la /data
# If empty or missing sanjai.db, proceed
```

2. **Download Latest Backup**

```bash
railway run -- bash -c "
  cd /app &&
  aws s3 cp s3://YOUR_BUCKET/sanjai-insight-backups/$(
    aws s3 ls s3://YOUR_BUCKET/sanjai-insight-backups/ |
    grep sanjai_backup_ |
    sort -r |
    head -1 |
    awk '{print \$4}'
  ) /data/latest_backup.db.gz
"
```

3. **Restore Database**

```bash
railway run -- bash -c "
  cd /data &&
  gunzip -c latest_backup.db.gz > sanjai.db &&
  rm latest_backup.db.gz
"
```

4. **Initialize Schema (if needed)**

```bash
railway run -- bash -c "
  cd /app &&
  sqlite3 /data/sanjai.db < schema_v2_operational.sql &&
  sqlite3 /data/sanjai.db < schema_alerts.sql
"
```

5. **Restart Service**

```bash
railway restart
```

6. **Verify**

```bash
railway logs
curl https://your-app.railway.app/health
```

---

### 4.4 Complete System Rebuild

**Prerequisites:**
- GitHub repository access
- Railway account
- S3 backups
- Environment variables (.env backup)

**Steps:**

1. **Create New Railway Service**

```bash
railway login
railway init
railway link
```

2. **Set Environment Variables**

```bash
# From backed up .env file
railway variables set TELEGRAM_BOT_TOKEN="..."
railway variables set OPENAI_API_KEY="..."
railway variables set DB_PATH="/data/sanjai.db"
railway variables set S3_BUCKET="..."
# ... (all variables)
```

3. **Add Railway Volume**

```bash
railway volume add --name sanjai-data --mount /data
```

4. **Deploy Application**

```bash
railway up
```

5. **Wait for Deployment**

```bash
railway logs --tail
# Wait until "Application startup complete"
```

6. **Restore Database**

```bash
railway run -- bash scripts/restore.sh --s3-latest --yes
```

7. **Restart Service**

```bash
railway restart
```

8. **Full Verification**

```bash
# Health check
curl https://your-app.railway.app/health

# Database integrity
railway run -- sqlite3 /data/sanjai.db "PRAGMA integrity_check;"

# Row counts
railway run -- sqlite3 /data/sanjai.db <<EOF
SELECT 'runlogs', COUNT(*) FROM runlogs
UNION ALL
SELECT 'insights', COUNT(*) FROM insights
UNION ALL
SELECT 'proposals', COUNT(*) FROM proposals;
EOF

# Test Telegram bot
# Send /status to bot
```

9. **Resume Operations**

```bash
# Trigger first job manually if needed
railway run -- python -c "from src.core.jobs import JobManager; jm = JobManager('/data/sanjai.db'); jm.create_job('WATCH', {'type': 'DAILY'})"
```

---

## Verification & Testing

### Monthly DR Drills

**Schedule:** First Monday of each month

**Procedure:**

1. **Backup Current Production**

```bash
bash scripts/backup.sh
```

2. **Create Test Environment**

```bash
# Use Railway preview environment
railway environment create dr-test
```

3. **Perform Restore**

```bash
DB_PATH=/tmp/test.db bash scripts/restore.sh --s3-latest --yes
```

4. **Validate Data**

```bash
sqlite3 /tmp/test.db "PRAGMA integrity_check;"
sqlite3 /tmp/test.db "SELECT COUNT(*) FROM runlogs;"
```

5. **Document Results**

- Restore time: _____ minutes
- Data integrity: PASS/FAIL
- Issues encountered: _____
- Action items: _____

6. **Cleanup**

```bash
railway environment delete dr-test
rm /tmp/test.db
```

### Backup Integrity Monitoring

**Automated Daily Checks:**

```bash
# Runs automatically in BackupManager
# Alerts sent to Telegram if integrity check fails
```

**Manual Verification:**

```bash
# Download latest backup
aws s3 cp s3://YOUR_BUCKET/sanjai-insight-backups/$(
  aws s3 ls s3://YOUR_BUCKET/sanjai-insight-backups/ |
  sort -r | head -1 | awk '{print $4}'
) /tmp/latest.db.gz

# Decompress and check
gunzip -c /tmp/latest.db.gz > /tmp/verify.db
sqlite3 /tmp/verify.db "PRAGMA integrity_check;"

# Cleanup
rm /tmp/latest.db.gz /tmp/verify.db
```

---

## Contact Information

### Escalation Path

| Role | Contact | Responsibilities |
|------|---------|------------------|
| **On-Call Engineer** | Telegram: @oncall | First responder |
| **System Owner** | 대표님 | Approval for major changes |
| **Railway Support** | support@railway.app | Infrastructure issues |

### External Dependencies

- **Railway Status:** https://status.railway.app
- **AWS S3 Status:** https://status.aws.amazon.com
- **Telegram API Status:** https://t.me/botstatus

### Recovery Checklist

- [ ] Identify failure scenario
- [ ] Notify stakeholders
- [ ] Stop application (if needed)
- [ ] Backup current state (even if corrupted)
- [ ] Execute recovery procedure
- [ ] Verify data integrity
- [ ] Restart application
- [ ] Test core functionality
- [ ] Monitor for 1 hour
- [ ] Document incident
- [ ] Update DR procedures if needed

---

## Appendix

### A. Critical Environment Variables

**Required for Recovery:**

```bash
TELEGRAM_BOT_TOKEN=      # Bot communication
OPENAI_API_KEY=          # LLM operations
DB_PATH=/data/sanjai.db  # Database location
S3_BUCKET=               # Backup storage
AWS_ACCESS_KEY_ID=       # S3 access
AWS_SECRET_ACCESS_KEY=   # S3 access
```

**Backup Location:**
- Primary: Railway secrets (encrypted)
- Secondary: Password manager
- Tertiary: Secure documentation

### B. Recovery Time Estimates

| Operation | Time (Typical) | Time (Worst Case) |
|-----------|----------------|-------------------|
| Download backup (S3) | 2 min | 10 min |
| Database restore | 1 min | 5 min |
| Integrity check | 30 sec | 2 min |
| Application restart | 1 min | 3 min |
| Full verification | 5 min | 15 min |
| **TOTAL** | **10 min** | **35 min** |

### C. Post-Recovery Actions

1. **Notify stakeholders** of recovery completion
2. **Document incident** in operations log
3. **Review alerts** during incident window
4. **Identify root cause** (corruption, deletion, etc.)
5. **Update DR procedures** if gaps identified
6. **Schedule postmortem** within 48 hours

---

**Document Version:** 1.0
**Last Tested:** 2026-03-03
**Next Test Due:** 2026-04-01
