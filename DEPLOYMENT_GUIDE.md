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
| `TELEGRAM_CEO_CHAT_ID` | Target chat ID for proposals | `123456789` |
| `DATABASE_PATH` | SQLite database path | `/data/insight.db` |
| `MONTHLY_BUDGET_KRW` | Monthly budget (KRW) | `50000` |

### 🟡 Optional (Has defaults)

| Variable | Description | Default |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini API key (optional) | None |
| `ENVIRONMENT` | Environment mode | `production` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `MAX_COST_USD` | Max cost per run | `5.0` |
| `MAX_TIME_SEC` | Max time per run (seconds) | `3600` |
| `MAX_RETRIES` | Max retry attempts | `3` |
| `MAX_REBUILDS` | Max rebuild attempts | `3` |
| `METRICS_ENABLED` | Enable Prometheus metrics | `true` |
| `METRICS_PORT` | Metrics endpoint port | `9090` |

### 🔵 Agent Integration (Optional)

| Variable | Description | Default |
|---|---|---|
| `SANJAI_AGENT_DB_PATH` | sanjai-agent DB path | `/data/agent/database.db` |
| `SANJAI_AGENT_VECTORDB_PATH` | sanjai-agent vector DB path | `/data/agent/chroma_db` |
| `AGENT_BRIDGE_SECRET` | HMAC secret for agent calls | None |

### 🟢 Obsidian Vault (Optional)

| Variable | Description | Default |
|---|---|---|
| `OBSIDIAN_VAULT_PATH` | Vault path for indexing | `/data/vault` |

### 🟣 OpenClaw Integration (Optional)

| Variable | Description | Default |
|---|---|---|
| `OPENCLAW_ENABLED` | Enable OpenClaw bridge | `false` |
| `OPENCLAW_WEBHOOK_URL` | OpenClaw webhook URL | None |

**참고:** `.env.railway.template` 파일에서 모든 환경변수 상세 설명 확인 가능

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
railway variables set TELEGRAM_CEO_CHAT_ID="123456789"
railway variables set DATABASE_PATH="/data/insight.db"
railway variables set MONTHLY_BUDGET_KRW="50000"
railway variables set ENVIRONMENT="production"

# Optional (if needed)
railway variables set GOOGLE_API_KEY="AIza..."
railway variables set OBSIDIAN_VAULT_PATH="/data/vault"
railway variables set SANJAI_AGENT_DB_PATH="/data/agent/database.db"
railway variables set AGENT_BRIDGE_SECRET="your-secret-key"
```

### 3. Deploy

#### Option A: 자동화 스크립트 (권장)

```bash
# Railway 배포 + 헬스체크
./scripts/railway_deploy.sh
```

#### Option B: 수동 배포

```bash
# 테스트 포함 배포
./scripts/deploy.sh

# 테스트 제외 배포
SKIP_TESTS=1 ./scripts/deploy.sh

# 또는 Railway CLI 직접 사용
railway up -d
```

#### Option C: GitHub 연동 (프로덕션 권장)

1. Push to GitHub first
2. Connect Railway to GitHub repo
3. Auto-deploy on push

### 4. Verify Deployment

#### Option A: 자동화 헬스체크 (권장)

```bash
# 전체 헬스체크
./scripts/health_check.sh https://your-app.railway.app

# 로컬 테스트
./scripts/health_check.sh http://localhost:8000
```

#### Option B: 수동 확인

```bash
# Check liveness
curl https://your-app.railway.app/healthz

# Check detailed health
curl https://your-app.railway.app/health | jq

# Check metrics (Prometheus format)
curl https://your-app.railway.app/metrics

# Check metrics (JSON format)
curl https://your-app.railway.app/metrics/json | jq

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

#### Prometheus Export

```bash
# Get Prometheus format metrics
curl https://your-app.railway.app/metrics

# Get JSON format metrics
curl https://your-app.railway.app/metrics/json | jq

# Get Grafana dashboard template
curl https://your-app.railway.app/metrics/grafana | jq
```

**14개 핵심 메트릭:**

1. `sanjai_insight_cost_total_usd` - 총 비용 (USD)
2. `sanjai_insight_cost_24h_usd` - 24시간 비용
3. `sanjai_insight_cost_per_insight_usd` - 인사이트당 비용
4. `sanjai_insight_acceptance_rate` - 승인율
5. `sanjai_insight_confidence_avg` - 평균 신뢰도
6. `sanjai_insight_high_confidence_ratio` - 고신뢰도 비율
7. `sanjai_insight_insights_total` - 총 인사이트 수
8. `sanjai_insight_insights_24h` - 24시간 인사이트
9. `sanjai_insight_response_latency_avg_sec` - 응답 시간
10. `sanjai_insight_jobs_pending` - 대기 작업
11. `sanjai_insight_jobs_running` - 실행 작업
12. `sanjai_insight_crawler_success_rate` - 크롤러 성공률
13. `sanjai_insight_db_size_mb` - DB 크기
14. `sanjai_insight_uptime_seconds` - 가동 시간

#### Threshold Optimizer

프로토타입 결과 분석 후 최적 threshold 계산:

```python
from src.utils import ThresholdOptimizer

optimizer = ThresholdOptimizer(db_path="data/insight.db")

# 프로토타입 결과 분석
results = await optimizer.analyze_prototype_results()

# 최적 threshold 계산 (F1 기반)
best_threshold = optimizer.calculate_optimal_threshold(
    results["insight_metrics"]["precision_recall_curve"],
    strategy="f1"
)

# config/thresholds.yaml 자동 업데이트
await optimizer.update_thresholds(
    {"insight.confidence_threshold": best_threshold},
    reason="Prototype optimization"
)

# A/B 테스트
ab_results = await optimizer.run_ab_test(
    control_threshold=0.7,
    test_threshold=0.75,
    sample_size=50
)
```

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
