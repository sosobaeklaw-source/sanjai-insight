# sanjai-insight

> 산재AI 능동적 인사이트 시스템 (v2.0)

소백노무법인의 자율주행 AI 시스템. 판례/정책/트렌드를 수집하고 분석하여, 능동적으로 법률 전략을 제안합니다.

## 개요

sanjai-insight는 다음과 같은 작업을 자동으로 수행합니다:

1. **Watch** - 대법원 판례, 근로복지공단 정책, 네이버 트렌드 등을 수집
2. **Think** - LLM을 통해 인사이트 도출 (근거 기반)
3. **Propose** - Telegram으로 대표님께 제안
4. **Execute** - 승인 후 sanjai-agent와 연동하여 사건 처리
5. **Diagnose** - 주간 자기진단 및 자동 최적화

## 주요 기능

### 운영화 핵심 원칙

- **멱등성** - 동일 작업 중복 실행 방지
- **재개 가능성** - 중단 지점부터 재시작
- **비용 제한** - 일/월 예산 초과 시 자동 중단
- **추적성** - correlation_id 기반 전체 이력 추적
- **관측성** - 헬스체크, 메트릭, 로그 API
- **근거 기반** - Evidence Gate (Fail-Closed)

### 핵심 엔진

1. **Watch Engine** - 크롤러 통합 + 증분 인덱싱
2. **Think Engine** - LLM 분석 + Evidence 검증
3. **Propose Engine** - Telegram 제안 + 버튼 UI
4. **Self-Diagnose Engine** - 자기진단 + Threshold 자동 조정

### 모니터링

- **14개 핵심 메트릭** - Prometheus/Grafana 연동
- **Threshold Optimizer** - ROC curve 기반 최적화
- **A/B 테스트** - 실험적 threshold 검증

## 빠른 시작

### 로컬 개발

```bash
# 1. Clone
git clone https://github.com/sosobaeklaw-source/sanjai-insight.git
cd sanjai-insight

# 2. 환경 설정
cp .env.example .env
# .env 파일 수정 (TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY 등)

# 3. 의존성 설치
pip install -r requirements.txt

# 4. DB 초기화
python scripts/init_db.py

# 5. 테스트
pytest tests/ -v

# 6. 실행
python -m src.app
```

### Railway 배포

```bash
# 1. Railway CLI 설치
npm install -g @railway/cli

# 2. Login & Link
railway login
railway link

# 3. 환경변수 설정
railway variables set ANTHROPIC_API_KEY="sk-ant-api03-..."
railway variables set TELEGRAM_BOT_TOKEN="..."
railway variables set TELEGRAM_CEO_CHAT_ID="..."
railway variables set DATABASE_PATH="/data/insight.db"
railway variables set MONTHLY_BUDGET_KRW="50000"

# 4. 배포
./scripts/railway_deploy.sh

# 5. 헬스체크
./scripts/health_check.sh https://your-app.railway.app
```

자세한 배포 가이드는 [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) 참조.

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                     sanjai-insight                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────┐    ┌───────────┐    ┌────────────┐         │
│  │   Watch   │ -> │   Think   │ -> │  Propose   │         │
│  │  (Crawl)  │    │  (Analyze)│    │ (Telegram) │         │
│  └───────────┘    └───────────┘    └────────────┘         │
│        ↓                ↓                  ↓               │
│  ┌─────────────────────────────────────────────┐          │
│  │         Evidence Store (SQLite FTS5)        │          │
│  └─────────────────────────────────────────────┘          │
│        ↓                                                    │
│  ┌───────────┐    ┌──────────────┐                        │
│  │ Self-     │    │ Threshold    │                        │
│  │ Diagnose  │    │ Optimizer    │                        │
│  └───────────┘    └──────────────┘                        │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  APIs: /healthz, /health, /metrics, /status, /cost        │
└─────────────────────────────────────────────────────────────┘
```

## 프로젝트 구조

```
sanjai-insight/
├── config/               # 설정 YAML (keywords, thresholds, schedule 등)
├── data/                 # SQLite DB + 수집 데이터
├── scripts/              # 배포/초기화 스크립트
├── src/
│   ├── api/              # 헬스체크, 메트릭, 상태 API
│   ├── bot/              # Telegram 봇 (commands, handlers)
│   ├── bridge/           # Agent 연동 (zero-trust)
│   ├── core/             # Worker, CheckpointManager, EventLogger
│   ├── crawlers/         # 크롤러 (precedent, policy, trend 등)
│   ├── engines/          # Watch, Think, Propose, Diagnose
│   ├── indexers/         # Vault 증분 인덱싱 + FTS5
│   ├── tools/            # LLM 클라이언트, 비용 추적
│   ├── utils/            # ThresholdOptimizer
│   ├── models.py         # Pydantic 모델 (40+ models)
│   ├── db.py             # DB 초기화
│   └── app.py            # Worker + Handlers 통합
├── tests/                # pytest 테스트 (25+ tests)
├── Dockerfile            # Railway 배포용
├── railway.toml          # Railway 설정
├── requirements.txt      # Python 의존성
├── schema.sql            # DB 스키마 (기본)
├── schema_v2_operational.sql  # 운영화 스키마 (v2.0)
├── .env.example          # 로컬 환경변수 템플릿
├── .env.railway.template # Railway 환경변수 템플릿
├── CLAUDE.md             # PRD (Product Requirements Document)
├── DEPLOYMENT_GUIDE.md   # 배포 가이드
├── HANDOFF_OPERATIONAL_v2.md  # 운영 인수인계
└── README.md             # 이 파일
```

## API 엔드포인트

### Health & Status

- `GET /healthz` - Liveness probe (200/503)
- `GET /health` - 상세 헬스 상태 (DB, Telegram, Vault 등)
- `GET /status?correlation_id=xxx` - Job 실행 상태
- `GET /cost?correlation_id=xxx` - 비용 분석 (stage별/model별)

### Metrics

- `GET /metrics` - Prometheus format (14개 메트릭)
- `GET /metrics/json` - JSON format
- `GET /metrics/grafana` - Grafana 대시보드 템플릿

### Telegram Bot Commands

- `/start` - 봇 시작
- `/help` - 도움말
- `/status` - 시스템 상태
- `/watch` - 수동 Watch 실행
- `/think` - 수동 Think 실행
- `/diagnose` - 자기진단 실행

## 환경변수

### 필수 (Required)

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CEO_CHAT_ID` | 대표님 Chat ID |
| `DATABASE_PATH` | SQLite DB 경로 |
| `MONTHLY_BUDGET_KRW` | 월 예산 (KRW) |

### 선택 (Optional)

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_API_KEY` | None | Gemini API key |
| `ENVIRONMENT` | production | development/production |
| `LOG_LEVEL` | INFO | 로깅 레벨 |
| `OBSIDIAN_VAULT_PATH` | None | Obsidian vault 경로 |
| `SANJAI_AGENT_DB_PATH` | None | sanjai-agent DB 경로 |
| `AGENT_BRIDGE_SECRET` | None | Agent 연동 비밀키 |
| `OPENCLAW_ENABLED` | false | OpenClaw 활성화 |
| `METRICS_ENABLED` | true | 메트릭 활성화 |

전체 환경변수는 `.env.railway.template` 참조.

## 개발 가이드

### 테스트 실행

```bash
# 전체 테스트
pytest tests/ -v

# 특정 테스트
pytest tests/test_operational_core.py -v

# 커버리지 포함
pytest tests/ --cov=src --cov-report=html
```

### 코드 품질

```bash
# Linting
ruff check src/

# Formatting
black src/ tests/

# Type checking (optional)
mypy src/
```

### 로컬 개발 팁

1. **DB 초기화**
   ```bash
   rm data/insight.db
   python scripts/init_db.py
   ```

2. **Manual Job Enqueue**
   ```python
   from src.core.jobs import JobManager
   manager = JobManager("data/insight.db")
   await manager.enqueue_job("WATCH", {"source": "PRECEDENT"})
   ```

3. **로그 확인**
   ```bash
   # 실시간 로그
   tail -f logs/app.log

   # DB 이벤트 로그
   sqlite3 data/insight.db "SELECT * FROM events ORDER BY ts DESC LIMIT 10"
   ```

## 운영 가이드

### 프로토타입 실행

```bash
# Watch 50건 수집
# (수동으로 WATCH job 50개 enqueue)

# Think 실행 (자동)
# Worker가 THINK job을 순차 처리

# 결과 분석
python -c "
from src.utils import ThresholdOptimizer
import asyncio

async def analyze():
    optimizer = ThresholdOptimizer('data/insight.db')
    results = await optimizer.analyze_prototype_results()
    print(results)

asyncio.run(analyze())
"
```

### Threshold 최적화

```python
from src.utils import ThresholdOptimizer

optimizer = ThresholdOptimizer("data/insight.db")

# 프로토타입 결과 분석
results = await optimizer.analyze_prototype_results()

# 최적 threshold 계산 (F1 최대화)
best = optimizer.calculate_optimal_threshold(
    results["insight_metrics"]["precision_recall_curve"],
    strategy="f1"
)

# config/thresholds.yaml 업데이트
await optimizer.update_thresholds(
    {"insight.confidence_threshold": best["threshold"]},
    reason="Prototype optimization (F1={:.3f})".format(best["f1"])
)
```

### 모니터링 설정

#### Prometheus 연동

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'sanjai-insight'
    static_configs:
      - targets: ['your-app.railway.app']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

#### Grafana 대시보드

```bash
# 대시보드 템플릿 다운로드
curl https://your-app.railway.app/metrics/grafana > sanjai-insight-dashboard.json

# Grafana에서 Import
# Dashboards → Import → Upload JSON file
```

### 알림 설정

```yaml
# Grafana Alert Rules
- alert: HighCost24h
  expr: sanjai_insight_cost_24h_usd > 5.0
  for: 5m
  annotations:
    summary: "24h cost exceeded $5"

- alert: LowAcceptanceRate
  expr: sanjai_insight_acceptance_rate < 0.3
  for: 1h
  annotations:
    summary: "Acceptance rate below 30%"

- alert: CrawlerDown
  expr: sanjai_insight_crawler_success_rate < 0.5
  for: 15m
  annotations:
    summary: "Crawler success rate below 50%"
```

## 문제 해결

### DB 잠금 오류

```bash
# WAL 모드 확인
sqlite3 data/insight.db "PRAGMA journal_mode"
# → wal

# 강제 WAL 활성화
sqlite3 data/insight.db "PRAGMA journal_mode=WAL"
```

### 메모리 부족

```bash
# Railway 메모리 제한 확인
railway run env | grep RAILWAY_MEMORY_LIMIT

# Worker 동시성 감소 (app.py)
# MAX_WORKERS = 1 (기본값)
```

### API 키 오류

```bash
# 환경변수 확인
railway variables get ANTHROPIC_API_KEY

# 로컬 확인
source .env && echo $ANTHROPIC_API_KEY
```

## 기여

이 프로젝트는 소백노무법인 내부용입니다. 외부 기여는 받지 않습니다.

## 라이선스

Copyright 2026 소백노무법인. All rights reserved.

## 문서

- [CLAUDE.md](CLAUDE.md) - 전체 PRD (7,000줄)
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - 배포 가이드
- [HANDOFF_OPERATIONAL_v2.md](HANDOFF_OPERATIONAL_v2.md) - 운영 인수인계
- [DEVIATION_LOG.md](DEVIATION_LOG.md) - 설계 변경 로그
- [LESSONS_LEARNED.md](LESSONS_LEARNED.md) - 개발 회고

## 연락처

- **프로젝트:** sanjai-insight
- **소속:** 소백노무법인
- **GitHub:** https://github.com/sosobaeklaw-source/sanjai-insight

---

**Built with ❤️ by Claude Code + Codex**
