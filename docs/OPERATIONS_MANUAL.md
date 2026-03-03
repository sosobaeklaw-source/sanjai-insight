# Operations Manual
## sanjai-insight System

> **Version:** 2.0
> **Last Updated:** 2026-03-03
> **Audience:** Operations Team, DevOps Engineers

---

## Table of Contents

1. [Daily Operations](#daily-operations)
2. [Monitoring & Alerts](#monitoring--alerts)
3. [Deployment](#deployment)
4. [Backup & Recovery](#backup--recovery)
5. [Performance Tuning](#performance-tuning)
6. [Troubleshooting](#troubleshooting)

---

## Daily Operations

### Morning Checklist (09:00 KST)

```bash
# 1. Check system health
curl https://your-app.railway.app/health

# 2. Review overnight jobs
railway run -- sqlite3 /data/sanjai.db "SELECT status, COUNT(*) FROM jobs WHERE created_at >= datetime('now', '-24 hours') GROUP BY status;"

# 3. Check cost (should be < $10/day)
curl https://your-app.railway.app/api/cost?days=1

# 4. Review alerts
# Check Telegram for alert notifications

# 5. Check logs for errors
railway logs --tail 100 | grep ERROR
```

### Weekly Tasks (Monday 10:00 KST)

- Review weekly cost report: `/api/cost?days=7`
- Check quality metrics: `/api/metrics?period=7d`
- Review approval rate trends
- Verify backup integrity
- Update dependencies if needed

### Monthly Tasks

- Rotate API keys and secrets
- Review audit logs for anomalies
- Update Railway resource limits if needed
- Review and update alerting thresholds
- Compliance checklist (see COMPLIANCE.md)

---

## Monitoring & Alerts

### Grafana Dashboard

**Access:** https://your-grafana.com/d/sanjai-insight-ops

**Key Panels:**
1. **Cost Trend:** Daily and cumulative costs
2. **Quality Metrics:** Validation pass rate, approval rate
3. **Performance:** LLM latency, call counts
4. **System Status:** Active runs, pending jobs
5. **Alerts:** Recent alerts and resolutions

### Alert Rules

**Configured in:** `src/monitoring/alert_rules.py`

| Alert | Threshold | Severity | Action |
|-------|-----------|----------|--------|
| Cost Overrun 24h | > $10 | WARNING | Review LLM usage |
| Quality Degradation | < 80% pass rate | ERROR | Check validation logic |
| Approval Rate Drop | < 70% | WARNING | Review proposals |
| High Latency | > 3000ms avg | WARNING | Check API health |
| DB Size Limit | > 500MB | WARNING | Run vacuum/cleanup |
| High Failure Rate | > 10% | ERROR | Check logs immediately |
| Crawler Failures | 3+ sources | ERROR | Fix crawler configs |
| Memory Warning | 50+ pending jobs | WARNING | Scale workers |

### Alert Response Procedures

**WARNING Alerts:**
1. Review metrics in Grafana
2. Check logs for patterns
3. Adjust thresholds if false positive
4. Document findings

**ERROR Alerts:**
1. Investigate immediately
2. Check system status: `/health`
3. Review correlation_id logs
4. Apply fix or rollback if needed
5. Create incident report

**CRITICAL Alerts:**
1. Page on-call engineer
2. Follow disaster recovery procedures
3. Notify stakeholders
4. Full incident postmortem

### Telegram Bot Commands for Operators

```
/status - System health and recent jobs
/cost [days] - Cost report (default 7 days)
/metrics - Quality metrics summary
/jobs - Pending and running jobs
/errors - Recent errors (last 24h)
```

---

## Deployment

### Pre-Deployment Checklist

```bash
# 1. Run tests locally
pytest tests/ -v

# 2. Check for breaking changes
git diff main..HEAD -- src/

# 3. Create backup
S3_PREFIX="sanjai-insight-pre-deploy" bash scripts/backup.sh

# 4. Review environment variables
railway variables

# 5. Check Railway status
curl https://status.railway.app
```

### Deployment Process

**Standard Deployment (Non-Breaking Changes):**

```bash
# 1. Merge to main
git checkout main
git pull origin main

# 2. Deploy via Railway
railway up

# 3. Monitor deployment
railway logs --tail

# 4. Verify health
curl https://your-app.railway.app/health

# 5. Smoke test
# Send /status to Telegram bot
# Check one proposal flow

# 6. Monitor for 30 minutes
railway logs --tail | grep -i error
```

**Blue-Green Deployment (Breaking Changes):**

```bash
# 1. Create new service
railway service create sanjai-insight-new

# 2. Deploy to new service
railway up --service sanjai-insight-new

# 3. Run migration if needed
railway run --service sanjai-insight-new -- python scripts/migrate_schema.py

# 4. Test new service
curl https://sanjai-insight-new.railway.app/health

# 5. Switch traffic (update Telegram webhook)
curl -X POST https://api.telegram.org/bot$TOKEN/setWebhook \
  -d "url=https://sanjai-insight-new.railway.app/telegram/webhook"

# 6. Monitor for 1 hour

# 7. Delete old service
railway service delete sanjai-insight-old
```

### Rollback Procedure

```bash
# 1. Identify last good deployment
railway deployments

# 2. Rollback to previous deployment
railway rollback --deployment <deployment-id>

# 3. Restore database if needed
bash scripts/restore.sh --s3-latest --yes

# 4. Verify health
curl https://your-app.railway.app/health

# 5. Notify stakeholders
```

### Post-Deployment Verification

```bash
# 1. Health check
curl https://your-app.railway.app/health
# Expected: {"status": "healthy", ...}

# 2. Database integrity
railway run -- sqlite3 /data/sanjai.db "PRAGMA integrity_check;"
# Expected: ok

# 3. API endpoints
curl https://your-app.railway.app/api/cost?days=1
curl https://your-app.railway.app/api/metrics

# 4. Telegram bot
# Send /status to bot, verify response

# 5. Monitor logs for 1 hour
railway logs --tail | grep -i error
```

---

## Backup & Recovery

### Automatic Backups

**Schedule:** Daily at 03:00 UTC
**Retention:** 30 days (local + S3)
**Managed by:** `src/utils/backup_manager.py`

**Verify Backup:**
```bash
# List recent backups
ls -lh backups/

# Or S3:
aws s3 ls s3://YOUR_BUCKET/sanjai-insight-backups/

# Check latest backup integrity
railway run -- bash scripts/backup.sh
```

### Manual Backup

```bash
# Before risky operations
DB_PATH=/data/sanjai.db bash scripts/backup.sh

# With custom S3 prefix
S3_PREFIX="sanjai-insight-manual-2026-03-03" bash scripts/backup.sh
```

### Restore from Backup

**See:** `DISASTER_RECOVERY.md` for detailed procedures

**Quick Restore:**
```bash
# From latest local backup
bash scripts/restore.sh --latest --yes

# From latest S3 backup
bash scripts/restore.sh --s3-latest --yes

# From specific date
bash scripts/restore.sh --date 20260303 --yes
```

---

## Performance Tuning

### Database Optimization

**Run Weekly:**
```bash
railway run -- sqlite3 /data/sanjai.db <<EOF
PRAGMA optimize;
ANALYZE;
VACUUM;
EOF
```

**Apply Indexes:**
```bash
railway run -- sqlite3 /data/sanjai.db < schema_indexes.sql
```

**Check Query Performance:**
```python
from src.utils.query_optimizer import QueryOptimizer

optimizer = QueryOptimizer("/data/sanjai.db")

# Analyze slow query
query = "SELECT * FROM llm_calls WHERE created_at > datetime('now', '-7 days')"
analysis = optimizer.get_slow_queries_estimate(query)
print(analysis["recommendations"])
```

### Worker Pool Tuning

**Current Settings:**
- Min workers: 2
- Max workers: 10
- Autoscaling: Enabled

**Adjust via Environment Variables:**
```bash
railway variables set WORKER_POOL_MIN=4
railway variables set WORKER_POOL_MAX=16
railway variables set WORKER_POOL_SIZE=8
```

**Monitor Worker Pool:**
```python
from src.core.worker_pool import get_worker_pool

pool = get_worker_pool()
metrics = pool.get_metrics()
print(f"Active: {metrics.active_workers}/{metrics.total_workers}")
print(f"CPU: {metrics.cpu_percent}%, Memory: {metrics.memory_percent}%")
```

### Cache Performance

**Enable Redis (Optional):**
```bash
railway variables set REDIS_URL="redis://..."
railway restart
```

**Monitor Cache:**
```python
from src.cache import get_cache_stats

stats = get_cache_stats()
print(f"Hit rate: {stats.get('hit_rate', 0):.1%}")
```

### Rate Limiting Adjustment

**Adjust Thresholds:**
```python
# In src/middleware/rate_limiter.py
_ip_limiter = RateLimiter(
    capacity=2000,  # Increase from 1000
    refill_rate=2000 / 3600
)
```

---

## Troubleshooting

### Common Issues

#### 1. High Cost Alert

**Symptoms:** Cost > $10/day

**Diagnosis:**
```bash
# Check cost breakdown by stage
curl https://your-app.railway.app/api/cost?days=1

# Check LLM call frequency
railway run -- sqlite3 /data/sanjai.db "
SELECT stage, COUNT(*), AVG(cost_usd)
FROM llm_calls
WHERE created_at >= datetime('now', '-24 hours')
GROUP BY stage;
"
```

**Fix:**
- Review prompt sizes (reduce context if possible)
- Check for retry loops
- Adjust LLM model (use cheaper models for non-critical stages)
- Implement more aggressive caching

#### 2. Quality Degradation

**Symptoms:** Validation pass rate < 80%

**Diagnosis:**
```bash
# Check validation failures
railway run -- sqlite3 /data/sanjai.db "
SELECT validation_errors
FROM strategy_packs
WHERE validation_status = 'FAIL'
  AND created_at >= datetime('now', '-24 hours')
LIMIT 10;
"
```

**Fix:**
- Review validation logic in `src/engines/validation.py`
- Check evidence quality
- Adjust validation thresholds if too strict
- Review recent LLM prompt changes

#### 3. Approval Rate Drop

**Symptoms:** Approval rate < 70%

**Diagnosis:**
```bash
# Check rejected proposals
railway run -- sqlite3 /data/sanjai.db "
SELECT p.title, p.summary, a.note
FROM proposals p
JOIN approvals a ON p.id = a.proposal_id
WHERE a.decision = 'REJECT'
  AND a.decided_at >= datetime('now', '-7 days')
LIMIT 10;
"
```

**Fix:**
- Review proposal quality
- Adjust proposal thresholds
- Gather feedback from users
- Improve insight generation

#### 4. Database Lock Errors

**Symptoms:** `database is locked` errors

**Diagnosis:**
```bash
# Check WAL mode
railway run -- sqlite3 /data/sanjai.db "PRAGMA journal_mode;"
# Expected: wal
```

**Fix:**
```bash
# Enable WAL mode if not already
railway run -- sqlite3 /data/sanjai.db "PRAGMA journal_mode=WAL;"

# Checkpoint WAL
railway run -- sqlite3 /data/sanjai.db "PRAGMA wal_checkpoint(FULL);"
```

#### 5. Memory Issues

**Symptoms:** OOM kills, slow performance

**Diagnosis:**
```bash
# Check memory usage
railway run -- ps aux | grep python

# Check DB size
railway run -- du -h /data/sanjai.db
```

**Fix:**
```bash
# Vacuum database
railway run -- sqlite3 /data/sanjai.db "VACUUM;"

# Run retention cleanup
railway run -- python -c "
from src.utils.gdpr_tools import cleanup_retention_policy
cleanup_retention_policy('/data/sanjai.db')
"

# Increase memory limit
railway variables set MEMORY_LIMIT=4096
```

### Log Analysis

**Find Errors:**
```bash
railway logs --tail 1000 | grep -i error
```

**Find Correlation ID:**
```bash
railway logs --tail 5000 | grep "DAILY_WATCH:2026-03-03"
```

**Parse JSON Logs:**
```bash
railway logs --tail 100 | jq 'select(.level == "ERROR")'
```

### Performance Profiling

**Enable Profiling:**
```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Run operation
from src.engines.think import run_think_stage
run_think_stage(correlation_id="test")

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
```

---

## Emergency Contacts

| Role | Contact | Availability |
|------|---------|--------------|
| **On-Call Engineer** | Telegram: @oncall | 24/7 |
| **System Owner** | 대표님 | Business hours |
| **Railway Support** | support@railway.app | 24/7 |

---

## Useful Commands Reference

```bash
# Health check
curl https://your-app.railway.app/health

# Cost report
curl "https://your-app.railway.app/api/cost?days=7"

# Database query
railway run -- sqlite3 /data/sanjai.db "SELECT COUNT(*) FROM runlogs;"

# View logs
railway logs --tail 100

# Restart service
railway restart

# Check disk usage
railway run -- df -h /data

# List environment variables
railway variables

# Create backup
bash scripts/backup.sh

# Restore backup
bash scripts/restore.sh --s3-latest --yes
```

---

**Last Reviewed:** 2026-03-03
**Next Review:** 2026-04-01
