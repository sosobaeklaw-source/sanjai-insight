# Troubleshooting Guide
## sanjai-insight Common Issues & Solutions

> **Version:** 2.0
> **Last Updated:** 2026-03-03

---

## Table of Contents

1. [Quick Diagnostics](#quick-diagnostics)
2. [Cost Issues](#cost-issues)
3. [Quality Issues](#quality-issues)
4. [Performance Issues](#performance-issues)
5. [Database Issues](#database-issues)
6. [Integration Issues](#integration-issues)
7. [Deployment Issues](#deployment-issues)

---

## Quick Diagnostics

### First Steps for Any Issue

```bash
# 1. Check system health
curl https://your-app.railway.app/health

# 2. Check recent logs
railway logs --tail 100 | grep -i error

# 3. Check database integrity
railway run -- sqlite3 /data/sanjai.db "PRAGMA integrity_check;"

# 4. Check disk space
railway run -- df -h /data

# 5. Check memory usage
railway run -- free -h
```

### Get Diagnostic Report

```bash
# Generate comprehensive diagnostic report
railway run -- python -c "
from src.utils.query_optimizer import QueryOptimizer, get_database_stats
from src.cache import get_cache_stats
from src.core.worker_pool import get_worker_pool
import json

conn = sqlite3.connect('/data/sanjai.db')

report = {
    'database': get_database_stats(conn),
    'cache': get_cache_stats(),
    'workers': get_worker_pool().get_metrics().__dict__
}

print(json.dumps(report, indent=2))
"
```

---

## Cost Issues

### Issue: Cost Spike (Unexpected High Cost)

**Symptoms:**
- Alert: "Cost Overrun 24h"
- Daily cost > $10

**Diagnosis:**
```bash
# 1. Check cost breakdown
curl "https://your-app.railway.app/api/cost?days=1"

# 2. Find expensive calls
railway run -- sqlite3 /data/sanjai.db "
SELECT
  stage,
  model,
  tokens_in + tokens_out as total_tokens,
  cost_usd,
  created_at
FROM llm_calls
WHERE created_at >= datetime('now', '-24 hours')
ORDER BY cost_usd DESC
LIMIT 20;
"

# 3. Check for retry loops
railway logs --tail 1000 | grep -i retry
```

**Common Causes:**
1. **Large context windows** - Check `tokens_in` values
2. **Retry loops** - LLM calls failing and retrying
3. **Expensive model usage** - Using GPT-4 for simple tasks

**Solutions:**

**Solution 1: Reduce context size**
```python
# In src/engines/think.py
def prepare_context(evidence: List[Evidence], max_tokens: int = 4000):
    # Truncate context to max_tokens
    context = []
    token_count = 0
    for ev in evidence:
        ev_tokens = len(ev.snippet) // 4  # Rough estimate
        if token_count + ev_tokens > max_tokens:
            break
        context.append(ev.snippet)
        token_count += ev_tokens
    return context
```

**Solution 2: Implement better caching**
```python
from src.cache import cache_llm_response, get_cached_llm_response

# Before calling LLM
cached = get_cached_llm_response(model, prompt)
if cached:
    return cached

# After LLM call
result = llm_client.call(model, prompt)
cache_llm_response(model, prompt, result, ttl=86400)  # 24h
```

**Solution 3: Use cheaper models for simple tasks**
```python
# In src/tools/llm_tools.py
def select_model(task_complexity: str) -> str:
    if task_complexity == "simple":
        return "gpt-3.5-turbo"  # Cheaper
    elif task_complexity == "moderate":
        return "gpt-4-turbo"
    else:
        return "gpt-4"  # Most expensive, use sparingly
```

---

### Issue: Cost Trending Up

**Symptoms:**
- Gradual cost increase over weeks
- No obvious spikes

**Diagnosis:**
```bash
# Check cost trend
curl "https://your-app.railway.app/api/cost?days=30"

# Check call frequency
railway run -- sqlite3 /data/sanjai.db "
SELECT
  DATE(created_at) as date,
  COUNT(*) as calls,
  SUM(cost_usd) as daily_cost
FROM llm_calls
WHERE created_at >= datetime('now', '-30 days')
GROUP BY DATE(created_at)
ORDER BY date;
"
```

**Solutions:**
- Review and optimize prompts
- Implement more aggressive deduplication
- Reduce job frequency if acceptable
- Consider model downgrades for non-critical stages

---

## Quality Issues

### Issue: Low Validation Pass Rate

**Symptoms:**
- Alert: "Quality Degradation"
- Validation pass rate < 80%

**Diagnosis:**
```bash
# Check validation failures
railway run -- sqlite3 /data/sanjai.db "
SELECT
  validation_errors,
  COUNT(*) as count
FROM strategy_packs
WHERE validation_status = 'FAIL'
  AND created_at >= datetime('now', '-7 days')
GROUP BY validation_errors
ORDER BY count DESC;
"

# Check evidence quality
railway run -- sqlite3 /data/sanjai.db "
SELECT
  ic.insight_id,
  ic.text as claim,
  COUNT(e.evidence_id) as evidence_count
FROM insight_claims ic
LEFT JOIN evidence e ON e.evidence_id IN (
  SELECT json_each.value
  FROM json_each(ic.evidence_ids_json)
)
WHERE ic.created_at >= datetime('now', '-24 hours')
GROUP BY ic.claim_id
HAVING evidence_count < 2;
"
```

**Common Causes:**
1. **Insufficient evidence** - Claims not backed by enough sources
2. **Low-quality sources** - Crawled content is poor
3. **Overly strict validation** - Thresholds too tight

**Solutions:**

**Solution 1: Improve evidence gathering**
```python
# In src/engines/think.py
def gather_evidence(query: str, min_evidence: int = 3) -> List[Evidence]:
    # Search vault
    vault_evidence = search_vault(query, limit=5)

    # Search crawled items
    crawled_evidence = search_source_items(query, limit=5)

    # Ensure minimum evidence count
    all_evidence = vault_evidence + crawled_evidence
    if len(all_evidence) < min_evidence:
        logger.warning(f"Insufficient evidence: {len(all_evidence)} < {min_evidence}")
        # Expand search or use fallback

    return all_evidence[:10]  # Cap at 10
```

**Solution 2: Adjust validation thresholds**
```python
# In src/engines/validation.py
VALIDATION_THRESHOLDS = {
    "min_evidence_per_claim": 2,  # Reduce from 3
    "min_snippet_length": 50,     # Reduce from 100
    "max_new_facts": 1            # Allow 1 new fact
}
```

**Solution 3: Improve source quality**
```bash
# Check crawler success rates
railway run -- sqlite3 /data/sanjai.db "
SELECT
  s.type,
  s.enabled,
  COUNT(si.item_id) as items_collected,
  s.last_success_at,
  s.last_error
FROM sources s
LEFT JOIN source_items si ON si.source_id = s.source_id
  AND si.fetched_at >= datetime('now', '-7 days')
GROUP BY s.source_id;
"

# Fix failing crawlers
# Update credentials, fix selectors, etc.
```

---

### Issue: Low Approval Rate

**Symptoms:**
- Alert: "Approval Rate Drop"
- User rejecting many proposals

**Diagnosis:**
```bash
# Analyze rejected proposals
railway run -- sqlite3 /data/sanjai.db "
SELECT
  p.title,
  p.summary,
  a.note as rejection_reason,
  a.decided_at
FROM proposals p
JOIN approvals a ON p.id = a.proposal_id
WHERE a.decision = 'REJECT'
  AND a.decided_at >= datetime('now', '-7 days')
ORDER BY a.decided_at DESC
LIMIT 20;
"
```

**Solutions:**
- Gather user feedback
- Adjust proposal thresholds
- Improve insight relevance
- Add pre-approval filters

---

## Performance Issues

### Issue: High Latency

**Symptoms:**
- Alert: "High Latency 1h"
- LLM calls > 3000ms avg

**Diagnosis:**
```bash
# Check latency breakdown
railway run -- sqlite3 /data/sanjai.db "
SELECT
  stage,
  model,
  AVG(latency_ms) as avg_latency,
  MAX(latency_ms) as max_latency,
  COUNT(*) as calls
FROM llm_calls
WHERE created_at >= datetime('now', '-1 hour')
  AND latency_ms IS NOT NULL
GROUP BY stage, model
ORDER BY avg_latency DESC;
"

# Check for slow queries
railway logs --tail 1000 | grep -i "slow query"
```

**Solutions:**

**Solution 1: Optimize LLM calls**
- Use streaming for long responses
- Reduce prompt size
- Use faster models (gpt-3.5-turbo vs gpt-4)

**Solution 2: Add database indexes**
```bash
railway run -- sqlite3 /data/sanjai.db < schema_indexes.sql
```

**Solution 3: Enable caching**
```bash
# Set up Redis
railway variables set REDIS_URL="redis://..."
railway restart
```

---

### Issue: High Memory Usage

**Symptoms:**
- OOM kills
- Railway restarts
- Slow performance

**Diagnosis:**
```bash
# Check memory
railway run -- free -h

# Check DB size
railway run -- du -h /data/sanjai.db

# Check largest tables
railway run -- python -c "
from src.utils.query_optimizer import QueryOptimizer
opt = QueryOptimizer('/data/sanjai.db')
tables = opt.get_table_sizes()
for t in sorted(tables, key=lambda x: x['row_count'], reverse=True)[:10]:
    print(f\"{t['name']}: {t['row_count']} rows\")
"
```

**Solutions:**

**Solution 1: Run cleanup**
```bash
railway run -- python -c "
from src.utils.gdpr_tools import cleanup_retention_policy
cleanup_retention_policy('/data/sanjai.db')
"

railway run -- sqlite3 /data/sanjai.db "VACUUM;"
```

**Solution 2: Increase memory limit**
```bash
railway variables set MEMORY_LIMIT=4096
railway restart
```

**Solution 3: Optimize worker pool**
```bash
railway variables set WORKER_POOL_MAX=8  # Reduce from 10
railway restart
```

---

## Database Issues

### Issue: Database Locked

**Symptoms:**
- Error: "database is locked"
- Timeout errors

**Diagnosis:**
```bash
# Check journal mode
railway run -- sqlite3 /data/sanjai.db "PRAGMA journal_mode;"

# Check for long-running transactions
railway logs --tail 500 | grep -i "transaction"
```

**Solutions:**

**Solution 1: Enable WAL mode**
```bash
railway run -- sqlite3 /data/sanjai.db "
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;
"
```

**Solution 2: Checkpoint WAL**
```bash
railway run -- sqlite3 /data/sanjai.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

**Solution 3: Use connection pooling**
```python
# In src/db.py
import sqlite3
from contextlib import contextmanager

_pool = []

@contextmanager
def get_connection():
    if _pool:
        conn = _pool.pop()
    else:
        conn = sqlite3.connect("/data/sanjai.db", timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")

    try:
        yield conn
    finally:
        _pool.append(conn)
```

---

### Issue: Database Corruption

**Symptoms:**
- Error: "database disk image is malformed"
- Integrity check fails

**Diagnosis:**
```bash
railway run -- sqlite3 /data/sanjai.db "PRAGMA integrity_check;"
```

**Solutions:**

**Solution: Restore from backup** (See DISASTER_RECOVERY.md)
```bash
# Stop application
railway restart

# Restore latest backup
bash scripts/restore.sh --s3-latest --yes

# Verify integrity
railway run -- sqlite3 /data/sanjai.db "PRAGMA integrity_check;"

# Restart
railway restart
```

---

## Integration Issues

### Issue: Telegram Bot Not Responding

**Symptoms:**
- Bot doesn't reply to commands
- Webhook errors in logs

**Diagnosis:**
```bash
# Check webhook status
curl "https://api.telegram.org/bot$TOKEN/getWebhookInfo"

# Check recent updates
railway run -- sqlite3 /data/sanjai.db "
SELECT update_id, chat_id, processed_at
FROM telegram_updates
ORDER BY processed_at DESC
LIMIT 10;
"

# Check logs for webhook errors
railway logs --tail 200 | grep webhook
```

**Solutions:**

**Solution 1: Verify webhook**
```bash
# Re-register webhook
curl -X POST "https://api.telegram.org/bot$TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"url\": \"https://your-app.railway.app/telegram/webhook\",
    \"secret_token\": \"$WEBHOOK_SECRET\"
  }"
```

**Solution 2: Check HMAC signature**
```python
# In logs, verify signature verification
# Should see: "Telegram webhook signature verified"
```

**Solution 3: Test locally**
```bash
# Send test update
curl -X POST "https://your-app.railway.app/telegram/webhook" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: $SECRET" \
  -d '{"update_id": 1, "message": {"chat": {"id": 123}, "text": "/status"}}'
```

---

### Issue: sanjai-agent Integration Failing

**Symptoms:**
- External requests stuck in PENDING
- Timeout errors

**Diagnosis:**
```bash
# Check external requests
railway run -- sqlite3 /data/sanjai.db "
SELECT
  request_id,
  target_system,
  job_type,
  status,
  created_at,
  sent_at,
  response_json
FROM external_requests
WHERE status IN ('PENDING', 'SENT')
  AND created_at >= datetime('now', '-24 hours')
ORDER BY created_at DESC;
"

# Check agent logs
# (On sanjai-agent side)
railway logs --tail 100 | grep external
```

**Solutions:**

**Solution 1: Verify shared secret**
```bash
# Ensure both services have same INTERNAL_SHARED_SECRET
railway variables | grep INTERNAL_SHARED_SECRET
```

**Solution 2: Check network connectivity**
```bash
railway run -- curl -v https://sanjai-agent.railway.app/external/jobs
```

**Solution 3: Retry failed requests**
```python
railway run -- python -c "
from src.bridge.agent_client import AgentClient

client = AgentClient('https://sanjai-agent.railway.app')

# Retry pending requests
import sqlite3
conn = sqlite3.connect('/data/sanjai.db')
cursor = conn.execute(
    'SELECT request_id, payload_hash FROM external_requests WHERE status = \"PENDING\"'
)
for request_id, payload_hash in cursor.fetchall():
    client.retry_request(request_id)
"
```

---

## Deployment Issues

### Issue: Deployment Failing

**Symptoms:**
- Railway build fails
- Service won't start

**Diagnosis:**
```bash
# Check build logs
railway logs --tail 200

# Check for missing dependencies
railway run -- pip list

# Check environment variables
railway variables
```

**Solutions:**

**Solution 1: Fix dependencies**
```bash
# Update requirements.txt
# Rebuild
railway up
```

**Solution 2: Check Dockerfile**
```dockerfile
# Ensure all build steps succeed
# Add debugging: RUN pip list
```

**Solution 3: Rollback**
```bash
railway deployments
railway rollback --deployment <previous-deployment-id>
```

---

### Issue: Health Check Failing After Deployment

**Symptoms:**
- Service shows as unhealthy
- /health returns 503

**Diagnosis:**
```bash
# Check what's failing
curl https://your-app.railway.app/health

# Check database connection
railway run -- sqlite3 /data/sanjai.db "SELECT 1;"

# Check logs for startup errors
railway logs --tail 100 | grep -i error
```

**Solutions:**

**Solution 1: Database migration**
```bash
# Apply schema updates
railway run -- sqlite3 /data/sanjai.db < schema_v2_operational.sql
railway run -- sqlite3 /data/sanjai.db < schema_alerts.sql
railway run -- sqlite3 /data/sanjai.db < schema_indexes.sql
```

**Solution 2: Fix environment variables**
```bash
# Ensure all required variables are set
railway variables set DB_PATH="/data/sanjai.db"
railway variables set TELEGRAM_BOT_TOKEN="..."
# etc.
```

---

## Advanced Diagnostics

### Enable Debug Logging

```bash
railway variables set LOG_LEVEL=DEBUG
railway restart
```

### Profile Performance

```python
# Add to src/app.py temporarily
import cProfile
profiler = cProfile.Profile()
profiler.enable()

# ... run operation ...

profiler.disable()
profiler.print_stats(sort='cumulative')
```

### Analyze Query Performance

```python
from src.utils.query_optimizer import QueryOptimizer

opt = QueryOptimizer("/data/sanjai.db")

query = "SELECT * FROM llm_calls WHERE created_at > datetime('now', '-7 days')"
analysis = opt.get_slow_queries_estimate(query)

print("Execution plan:", analysis["execution_plan"])
print("Recommendations:", analysis["recommendations"])
```

---

## Getting Help

### Before Asking for Help

1. Check this troubleshooting guide
2. Review logs: `railway logs --tail 500`
3. Check system health: `curl /health`
4. Try basic diagnostics (see "Quick Diagnostics")
5. Document what you've tried

### Contact Information

- **Telegram:** @oncall
- **Email:** support@sosobaek.com
- **Railway Support:** support@railway.app

### Information to Provide

When reporting an issue, include:
- Error message (full text)
- Correlation ID (if applicable)
- Timestamp of issue
- Steps to reproduce
- Recent deployments or changes
- Relevant logs

---

**Last Updated:** 2026-03-03
**Next Review:** 2026-04-01
