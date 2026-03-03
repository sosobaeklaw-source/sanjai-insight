# sanjai-insight Deployment Guide

**Date:** 2026-03-03
**Target:** Railway (Production)
**Status:** Ready for Deployment

---

## Pre-Deployment Checklist

### ✅ Code Integration
- [x] Watch Engine integrated (watch_handler in app.py)
- [x] Think Engine integrated (think_handler in app.py)
- [x] Propose Engine integrated (propose_handler in app.py)
- [x] Self-Diagnose Engine integrated (diagnose_handler in app.py)
- [x] All tests passing (25/25 PASSED)

### ✅ Infrastructure
- [x] Dockerfile configured (Python 3.12-slim + sqlite3)
- [x] railway.toml configured
- [x] requirements.txt up-to-date
- [x] DB schema ready (schema.sql + schema_v2_operational.sql)

---

## Environment Variables (Railway)

### 🔴 Required (Deployment will fail without these)

| Variable | Description | Example |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API key for Think Engine | `sk-ant-api03-...` |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | `7123456789:AAH...` |
| `TELEGRAM_CHAT_ID` | Target chat ID for proposals | `123456789` |
| `DB_PATH` | SQLite database path | `data/insight.db` |

### 🟡 Optional (Has defaults)

| Variable | Description | Default |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini API key (optional) | None |
| `MAX_COST_USD` | Max cost per run | `5.0` |
| `MAX_TIME_SEC` | Max time per run (seconds) | `3600` |
| `MAX_RETRIES` | Max retry attempts | `3` |
| `MAX_REBUILDS` | Max rebuild attempts | `3` |

### 🔵 Agent Integration (Optional)

| Variable | Description | Default |
|---|---|---|
| `AGENT_BASE_URL` | sanjai-agent API URL | None |
| `AGENT_HMAC_SECRET` | HMAC secret for agent calls | None |

---

## Deployment Steps

### 1. Railway Project Setup

```bash
# Install Railway CLI (if not installed)
npm install -g @railway/cli

# Login
railway login

# Link project
cd "C:\Users\user\손원일\documents\sanjai-insight"
railway link
```

### 2. Set Environment Variables

```bash
# Required
railway variables set ANTHROPIC_API_KEY="sk-ant-api03-..."
railway variables set TELEGRAM_BOT_TOKEN="7123456789:AAH..."
railway variables set TELEGRAM_CHAT_ID="123456789"
railway variables set DB_PATH="data/insight.db"

# Optional (if needed)
railway variables set GOOGLE_API_KEY="AIza..."
railway variables set MAX_COST_USD="10.0"
railway variables set AGENT_BASE_URL="https://sanjai-agent.railway.app"
railway variables set AGENT_HMAC_SECRET="your-secret-key"
```

### 3. Deploy

```bash
# Push to Railway
railway up

# Or deploy from GitHub (recommended)
# 1. Push to GitHub first
# 2. Connect Railway to GitHub repo
# 3. Auto-deploy on push
```

### 4. Verify Deployment

```bash
# Check health
curl https://your-app.railway.app/healthz

# Check detailed health
curl https://your-app.railway.app/health

# Check logs
railway logs
```

---

## Post-Deployment Verification

### Health Check API

```bash
# Liveness (should return 200)
GET /healthz

# Detailed health status
GET /health
# Response:
# {
#   "status": "ok",
#   "db_connected": true,
#   "vault_indexed": 0,
#   "insights_24h": 0,
#   "cost_24h_usd": 0.0
# }
```

### Test Workflow

1. **Enqueue a Watch Job** (via Worker or API)
   - Job should collect items from sources
   - Evidence should be created

2. **Check Events**
   ```bash
   GET /status?correlation_id=WATCH:xxx
   ```

3. **Monitor Costs**
   ```bash
   GET /cost?correlation_id=THINK:xxx
   ```

---

## Database Initialization

The application automatically initializes the database on first run:

1. Creates `data/insight.db` if not exists
2. Applies `schema.sql`
3. Applies `schema_v2_operational.sql`
4. Enables WAL mode
5. Creates FTS5 triggers

**Volume Setup (Railway):**
- Ensure `data/` directory is persistent
- Use Railway volumes to persist database

---

## Monitoring & Observability

### Built-in APIs

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Liveness probe (200/503) |
| `GET /health` | Health status + metrics |
| `GET /status?correlation_id=xxx` | Job execution status |
| `GET /cost?correlation_id=xxx` | Cost breakdown |

### Logs

- Application logs to stdout (Railway captures)
- Event logger writes to `events` table (append-only)
- LLM calls logged to `llm_calls` table

### Metrics

- `system_metrics` table tracks daily aggregates
- Self-Diagnose engine runs periodic health checks

---

## Cost Management

### Expected Costs (Estimated)

| Component | Cost per Run | Monthly (30 days @ 1 run/day) |
|---|---|---|
| Watch (crawling) | Free | Free |
| Think (Claude Sonnet 4.5) | $0.10-0.50 | $3-15 |
| Propose (Telegram) | Free | Free |
| Self-Diagnose | $0.01-0.05 | $0.30-1.50 |
| **Total** | **~$0.15-0.60** | **~$4-20/month** |

### Cost Controls

1. **TerminationChecker**: Stops execution if `max_cost_usd` exceeded
2. **LLM Call Tracking**: All costs logged to `llm_calls` table
3. **Self-Diagnose**: Alerts if 7-day cost exceeds threshold

---

## Troubleshooting

### Database Issues

**Issue:** `sqlite3.OperationalError: database is locked`

**Solution:**
- Ensure WAL mode is enabled
- Check only one Worker instance is running
- Restart application

### API Key Issues

**Issue:** `AuthenticationError: Invalid API key`

**Solution:**
- Verify `ANTHROPIC_API_KEY` is set correctly
- Check key has not expired
- Test key: `curl https://api.anthropic.com/v1/messages -H "x-api-key: $KEY"`

### Telegram Bot Issues

**Issue:** Bot not responding

**Solution:**
- Verify `TELEGRAM_BOT_TOKEN` is correct
- Check bot is added to target chat
- Verify `TELEGRAM_CHAT_ID` matches chat

### Cost Exceeded

**Issue:** Execution stops with "Termination: max_cost_usd exceeded"

**Solution:**
- Increase `MAX_COST_USD` environment variable
- Review LLM usage: `SELECT * FROM llm_calls ORDER BY cost_usd DESC`
- Optimize prompts to reduce token usage

---

## Rollback Procedure

If deployment fails or issues arise:

1. **Railway Rollback**
   ```bash
   railway rollback
   ```

2. **Git Rollback** (if needed)
   ```bash
   git revert HEAD
   git push origin main
   ```

3. **Database Restore** (if needed)
   - Restore from Railway volume snapshot
   - Or re-initialize from backup

---

## Next Steps After Deployment

1. **Monitor Initial Runs**
   - Watch first WATCH job execution
   - Check first THINK job (LLM calls)
   - Verify PROPOSE sends to Telegram

2. **Adjust Thresholds**
   - Based on actual data, tune `min_confidence` in Propose payload
   - Adjust `max_cost_usd` based on actual usage

3. **Enable Scheduling** (Future)
   - Add APScheduler jobs for periodic Watch
   - Example: `@daily` watch job

4. **Agent Integration** (Future)
   - Configure `AGENT_BASE_URL` + `AGENT_HMAC_SECRET`
   - Test OpenClaw bridge
   - Implement Strategy Gate

---

## Support Contacts

- **Deployment Issues:** Check Railway docs + logs
- **Application Errors:** Review `events` table + `/status` API
- **Cost Concerns:** Review `llm_calls` + `/cost` API

---

**Document Status:** ✅ Ready for Production Deployment
**Last Updated:** 2026-03-03
