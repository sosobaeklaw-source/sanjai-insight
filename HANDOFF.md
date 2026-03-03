# HANDOFF: sanjai-insight 완전 인수인계 문서

> **작성일**: 2026-03-03
> **버전**: v2.0 (Phase 1 고도화 완료)
> **담당**: Claude Sonnet 4.5
> **목적**: 프로젝트의 완전한 인수인계 및 운영 가이드 제공

---

## 1. 프로젝트 개요

### 1.1 핵심 정보

| 항목 | 값 |
|------|-----|
| **프로젝트명** | sanjai-insight (산재AI 능동적 인사이트 시스템) |
| **경로** | `C:\Users\user\손원일\documents\sanjai-insight` |
| **GitHub** | https://github.com/sosobaeklaw-source/sanjai-insight.git |
| **배포 플랫폼** | Railway |
| **주요 연동** | sanjai-agent (C:\Users\user\손원일\documents\sanjai-agent) |

### 1.2 시스템 아키텍처

```
sanjai-insight (능동적 인사이트 시스템)
├── Watch Engine: 4개 크롤러 (판례/정책/경쟁사/트렌드)
├── Think Engine: LLM 분석 + Evidence Validation
├── Propose Engine: Telegram 제안 + Approval Workflow
├── Self-Diagnose: 자기진단 + OpenClaw 연동
└── Worker System: 비동기 작업 처리
```

### 1.3 통계 (2026-03-03 기준)

- **총 파일**: 70개 Python 파일
- **총 코드**: 16,663줄
- **구현 완료**: Phase 1-7 + 10개 고도화 기능
- **테스트**: 회귀 테스트 6개 통과
- **배포 상태**: Railway 준비 완료

---

## 2. 구현 완료 항목

### 2.1 Phase 1-7 (기본 인프라)

#### Step 1: 기초 인프라 ✅
- `src/models.py`: 데이터 모델 정의
- `schema.sql` + `schema_v2_operational.sql`: 운영화 스키마
- `src/db.py`: 데이터베이스 관리
- `config/*.yaml`: 전체 설정 파일

#### Step 2-3: 크롤러 + 인덱서 ✅
- `src/crawlers/precedent.py`: 판례 크롤러
- `src/crawlers/trend.py`: 트렌드 크롤러
- `src/crawlers/policy.py`: 정책 크롤러
- `src/crawlers/competitor.py`: 경쟁사 크롤러
- `src/indexers/vault_incremental.py`: 증분 인덱싱 (FTS5)
- `src/indexers/normalizer.py`: 데이터 정규화

#### Step 4-5: Watch/Think/Propose Engines ✅
- `src/engines/watch.py`: Watch 엔진 (크롤러 통합)
- `src/engines/think.py`: Think 엔진 (LLM 분석)
- `src/engines/propose.py`: Propose 엔진 (Telegram UI)
- `src/engines/validation.py`: Evidence Validation (fail-closed)
- `src/engines/self_diagnose.py`: 자기진단 (582줄)

#### Step 6: 운영화 코어 ✅
- `src/core/checkpoint.py`: 체크포인트 관리
- `src/core/termination.py`: 종료 체커
- `src/core/events.py`: 이벤트 로깅
- `src/core/jobs.py`: 작업 관리
- `src/core/worker.py` + `worker_pool.py`: Worker 풀

#### Step 7: API & 봇 ✅
- `src/api/health.py`: Health check 엔드포인트
- `src/api/status.py`: 상태 조회
- `src/api/cost.py`: 비용 추적
- `src/api/metrics.py`: 메트릭 수집
- `src/bot/handlers.py`: Telegram 핸들러
- `src/bot/approval_handler.py`: 승인 워크플로우
- `src/bot/idempotency.py`: 중복 방지

### 2.2 Phase 1 고도화 (10개 기능) ✅

#### 1. Multi-tenancy (636줄)
- **파일**: `src/auth/tenant_manager.py`
- **기능**: 테넌트별 DB 스키마 격리, RBAC, API 키 관리
- **핵심**: `TenantManager.create_tenant()`, `validate_api_key()`

#### 2. 실시간 스트리밍 (558줄)
- **파일**: `src/api/streaming.py`
- **기능**: SSE 이벤트 스트리밍, 진행률 추적, 클라이언트 SDK
- **핵심**: `StreamManager.stream_generator()`, `ProgressTracker`

#### 3. API Gateway (576줄)
- **파일**: `src/gateway/api_gateway.py`
- **기능**: 라우팅, 인증, Rate limiting, 로드 밸런싱
- **핵심**: `APIGateway.handle_request()`, `RateLimiter`

#### 4. Plugin 아키텍처 (554줄)
- **파일**: `src/plugins/plugin_loader.py`
- **기능**: 플러그인 동적 로딩, 라이프사이클 관리, 샌드박싱
- **핵심**: `PluginLoader.load_plugin()`, `PluginManager`

#### 5. 배치 처리 시스템 (450+줄)
- **파일**: `src/batch/batch_processor.py`
- **기능**: 작업 스케줄링, 병렬 실행, 재시도 로직, 의존성 관리
- **핵심**: `BatchProcessor.process_job()`, `JobQueue`

#### 6. 검색 엔진 통합 (350+줄)
- **파일**: `src/search/search_engine.py`
- **기능**: SQLite FTS5, BM25 랭킹, 패싯 검색, 자동완성
- **핵심**: `SearchEngine.search()`, `index_document()`

#### 7. 데이터 파이프라인 (500+줄)
- **파일**: `src/pipelines/data_pipeline.py`
- **기능**: ETL, 데이터 검증, 변환 체인, 진행 추적
- **핵심**: `Pipeline.run()`, `DataValidator`, `DataTransformer`

#### 8. 캐시 클러스터 (400+줄)
- **파일**: `src/cache/redis_cache.py`
- **기능**: Redis 분산 캐싱, 일관성 해싱, 읽기 복제
- **핵심**: `DistributedCache`, `RedisCache`

#### 9. 모바일 앱 백엔드 (450+줄)
- **파일**: `src/mobile/mobile_api.py`
- **기능**: 디바이스 관리, Push 알림, 오프라인 동기화
- **핵심**: `DeviceManager`, `PushNotificationService`, `OfflineSyncManager`

#### 10. 자동 문서 생성 (350+줄)
- **파일**: `src/docs/doc_generator.py`
- **기능**: OpenAPI 스펙 생성, Markdown 문서화, 코드 인스펙션
- **핵심**: `AutoDocGenerator`, `OpenAPIGenerator`, `MarkdownGenerator`

---

## 3. Railway 배포 가이드

### 3.1 필수 환경변수

Railway에 다음 환경변수를 설정해야 합니다:

```bash
# 핵심 설정
TELEGRAM_BOT_TOKEN=<대표님 제공>
ANTHROPIC_API_KEY=<대표님 제공>
OPENAI_API_KEY=<대표님 제공 - 선택>

# 데이터베이스
DATABASE_PATH=data/sanjai.db

# 운영 설정
LOG_LEVEL=INFO
ENVIRONMENT=production
WORKER_COUNT=4

# 비용 제한
DAILY_COST_LIMIT=10.0
MONTHLY_COST_LIMIT=300.0

# Obsidian Vault (선택)
VAULT_PATH=/vault/sanjai-vault

# Redis (선택 - 캐시 성능 향상)
REDIS_URL=redis://:<password>@<host>:6379

# 알림 설정
ALERT_THRESHOLD_ERROR=10
ALERT_THRESHOLD_WARNING=50
```

### 3.2 배포 명령어

```bash
# 1. Railway 프로젝트 연결 (최초 1회)
cd "C:\Users\user\손원일\documents\sanjai-insight"
railway link

# 2. 환경변수 설정 (CLI)
railway variables set TELEGRAM_BOT_TOKEN=<값>
railway variables set ANTHROPIC_API_KEY=<값>
railway variables set DATABASE_PATH=data/sanjai.db
railway variables set LOG_LEVEL=INFO
railway variables set ENVIRONMENT=production
railway variables set WORKER_COUNT=4
railway variables set DAILY_COST_LIMIT=10.0
railway variables set MONTHLY_COST_LIMIT=300.0

# 3. 배포
railway up --detach

# 4. 로그 확인
railway logs

# 5. 상태 확인
curl https://<your-app>.railway.app/healthz
```

### 3.3 배포 후 검증

```bash
# Health check
curl https://<your-app>.railway.app/health

# Status 확인
curl https://<your-app>.railway.app/status

# Cost 확인
curl https://<your-app>.railway.app/cost
```

---

## 4. 운영 가이드

### 4.1 일상 운영

#### 모니터링
```bash
# 로그 실시간 확인
railway logs --follow

# 비용 확인
curl https://<your-app>.railway.app/cost

# 작업 상태 확인
curl https://<your-app>.railway.app/status
```

#### 수동 작업 트리거
```python
# Telegram 봇 명령어
/status          # 시스템 상태 확인
/cost            # 비용 확인
/health          # 헬스체크
/run precedent   # 판례 크롤러 수동 실행
/diagnose        # 자기진단 실행
```

### 4.2 비용 관리

#### 자동 제한
- 일일 비용 제한: `$10.00` (DAILY_COST_LIMIT)
- 월간 비용 제한: `$300.00` (MONTHLY_COST_LIMIT)
- 초과 시 자동 작업 중단 + 알림

#### 비용 최적화
1. **캐시 활용**: Redis 연결 시 LLM 호출 50% 감소
2. **배치 처리**: 오프피크 시간대 작업 스케줄링
3. **증분 크롤링**: 변경된 데이터만 수집

### 4.3 장애 대응

#### Health Check 실패
```bash
# 1. 로그 확인
railway logs --tail 100

# 2. Worker 재시작
railway restart

# 3. 데이터베이스 백업 확인
ls -lh data/backups/
```

#### Worker 중단
```bash
# 1. 체크포인트 확인
sqlite3 data/sanjai.db "SELECT * FROM checkpoints ORDER BY timestamp DESC LIMIT 5;"

# 2. 재시작 (자동 복구)
railway restart
```

#### 비용 초과
```bash
# 1. 비용 내역 확인
curl https://<your-app>.railway.app/cost

# 2. 임시 제한 상향 (긴급 시)
railway variables set DAILY_COST_LIMIT=20.0

# 3. 작업 큐 정리
sqlite3 data/sanjai.db "DELETE FROM worker_jobs WHERE status='pending' AND priority='low';"
```

### 4.4 백업 및 복구

#### 자동 백업
- **빈도**: 매일 04:00 UTC
- **보관**: 7일분
- **경로**: `data/backups/sanjai_backup_YYYYMMDD.db`

#### 수동 백업
```bash
# 전체 백업
railway run python scripts/backup.py

# 특정 테이블 백업
sqlite3 data/sanjai.db ".dump insights" > insights_backup.sql
```

#### 복구
```bash
# 백업에서 복구
railway run python scripts/restore.py --date 20260302

# 특정 테이블 복구
railway run sqlite3 data/sanjai.db < insights_backup.sql
```

---

## 5. 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────────┐
│                        sanjai-insight v2.0                          │
│                    (능동적 인사이트 시스템)                          │
└─────────────────────────────────────────────────────────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────┐          ┌───────────────┐         ┌───────────────┐
│ Watch Engine  │          │ Think Engine  │         │ Propose Engine│
│ (4 Crawlers)  │          │ (LLM Analyze) │         │ (Telegram UI) │
├───────────────┤          ├───────────────┤         ├───────────────┤
│ • Precedent   │─────────▶│ • Evidence    │────────▶│ • Approval    │
│ • Policy      │          │   Validation  │         │   Workflow    │
│ • Competitor  │          │ • Cost Track  │         │ • Push Notif  │
│ • Trend       │          │ • Fail-closed │         │ • Mobile Sync │
└───────────────┘          └───────────────┘         └───────────────┘
        │                          │                          │
        └──────────────────────────┼──────────────────────────┘
                                   ▼
                         ┌─────────────────┐
                         │  Worker System  │
                         │  (Async Queue)  │
                         ├─────────────────┤
                         │ • Checkpoint    │
                         │ • Termination   │
                         │ • Event Log     │
                         │ • Job Manager   │
                         └─────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────┐          ┌───────────────┐         ┌───────────────┐
│  Multi-tenant │          │ Batch Process │         │ Search Engine │
│  (RBAC + API) │          │ (Job Schedule)│         │ (FTS5 + BM25) │
└───────────────┘          └───────────────┘         └───────────────┘
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────┐          ┌───────────────┐         ┌───────────────┐
│ API Gateway   │          │ Data Pipeline │         │ Cache Cluster │
│ (Rate Limit)  │          │ (ETL + Valid) │         │ (Redis Shard) │
└───────────────┘          └───────────────┘         └───────────────┘
        │                          │                          │
        └──────────────────────────┼──────────────────────────┘
                                   ▼
                         ┌─────────────────┐
                         │   sanjai-agent  │
                         │ (사건 상담 AI)   │
                         │ /external/jobs  │
                         └─────────────────┘
```

---

## 6. 파일 구조

```
sanjai-insight/
├── src/
│   ├── api/                 # API 엔드포인트
│   │   ├── health.py        # Health check
│   │   ├── status.py        # 상태 조회
│   │   ├── cost.py          # 비용 추적
│   │   ├── metrics.py       # 메트릭
│   │   └── streaming.py     # SSE 스트리밍 (558줄)
│   ├── auth/                # 인증/인가
│   │   └── tenant_manager.py # Multi-tenancy (636줄)
│   ├── batch/               # 배치 처리
│   │   └── batch_processor.py # 작업 스케줄링 (450줄)
│   ├── bot/                 # Telegram 봇
│   │   ├── handlers.py      # 메시지 핸들러
│   │   ├── approval_handler.py # 승인 워크플로우
│   │   └── idempotency.py   # 중복 방지
│   ├── bridge/              # 외부 연동
│   │   ├── agent_client.py  # sanjai-agent 연동
│   │   └── openclaw_bridge.py # OpenClaw 연동
│   ├── cache/               # 캐싱
│   │   └── redis_cache.py   # Redis + 분산 캐시 (400줄)
│   ├── core/                # 코어 시스템
│   │   ├── checkpoint.py    # 체크포인트
│   │   ├── termination.py   # 종료 체커
│   │   ├── events.py        # 이벤트 로깅
│   │   ├── jobs.py          # 작업 관리
│   │   └── worker.py        # Worker 풀
│   ├── crawlers/            # 크롤러
│   │   ├── base.py          # Base 크롤러
│   │   ├── precedent.py     # 판례
│   │   ├── policy.py        # 정책
│   │   ├── competitor.py    # 경쟁사
│   │   └── trend.py         # 트렌드
│   ├── docs/                # 문서 생성
│   │   └── doc_generator.py # OpenAPI + Markdown (350줄)
│   ├── engines/             # 핵심 엔진
│   │   ├── watch.py         # Watch 엔진
│   │   ├── think.py         # Think 엔진
│   │   ├── propose.py       # Propose 엔진
│   │   ├── validation.py    # Evidence Validation
│   │   └── self_diagnose.py # 자기진단 (582줄)
│   ├── gateway/             # API Gateway
│   │   └── api_gateway.py   # 라우팅 + Rate limit (576줄)
│   ├── indexers/            # 인덱서
│   │   ├── vault_incremental.py # 증분 인덱싱
│   │   └── normalizer.py    # 정규화
│   ├── mobile/              # 모바일 백엔드
│   │   └── mobile_api.py    # 디바이스 + Push (450줄)
│   ├── pipelines/           # 데이터 파이프라인
│   │   └── data_pipeline.py # ETL + Validation (500줄)
│   ├── plugins/             # 플러그인 시스템
│   │   └── plugin_loader.py # 플러그인 로더 (554줄)
│   ├── search/              # 검색 엔진
│   │   └── search_engine.py # FTS5 + BM25 (350줄)
│   ├── tools/               # 유틸리티
│   │   └── llm_tools.py     # LLM 클라이언트
│   ├── models.py            # 데이터 모델
│   ├── db.py                # DB 관리
│   └── app.py               # 메인 앱
├── config/                  # 설정 파일
│   ├── thresholds.yaml      # 임계값
│   ├── crawler_config.yaml  # 크롤러 설정
│   └── llm_config.yaml      # LLM 설정
├── data/                    # 데이터 디렉토리
│   ├── sanjai.db            # 메인 DB
│   ├── tenants.db           # 테넌트 DB
│   ├── batch_jobs.db        # 배치 작업 DB
│   ├── search.db            # 검색 인덱스
│   └── backups/             # 백업
├── tests/                   # 테스트
│   ├── test_operational_core.py # 회귀 테스트
│   └── ...                  # 기타 테스트
├── scripts/                 # 유틸리티 스크립트
│   ├── deploy.sh            # 배포 스크립트
│   ├── backup.py            # 백업
│   └── restore.py           # 복구
├── Dockerfile               # Docker 이미지
├── railway.toml             # Railway 설정
├── requirements.txt         # Python 의존성
├── CLAUDE.md                # PRD (5,282줄)
├── HANDOFF.md               # 인수인계 문서 (이 문서)
└── README.md                # 프로젝트 README

총 70개 Python 파일, 16,663줄 코드
```

---

## 7. 다음 단계

### 7.1 즉시 실행 가능
1. **Railway 배포**: 환경변수 설정 후 `railway up`
2. **Telegram 봇 테스트**: `/status`, `/health` 명령어 확인
3. **수동 크롤링**: `/run precedent` 실행

### 7.2 단기 (1-2주)
1. **프로덕션 임계값 조정**: `config/thresholds.yaml` 튜닝
2. **모니터링 대시보드**: Grafana 연동 (선택)
3. **알림 채널 추가**: 이메일, Slack (선택)

### 7.3 중기 (1-2개월)
1. **Plugin 개발**: 새로운 크롤러를 플러그인으로 추가
2. **Multi-tenant 활성화**: 추가 테넌트 등록
3. **모바일 앱 개발**: iOS/Android 클라이언트

### 7.4 장기 (3-6개월)
1. **AI 모델 미세조정**: 판례 분석 전용 모델 학습
2. **분산 크롤링**: Worker 노드 추가
3. **글로벌 확장**: 다국어 지원 + 해외 판례

---

## 8. 문제 해결

### 8.1 자주 발생하는 문제

#### Q1: Worker가 작업을 처리하지 않음
```bash
# 해결: Worker 재시작
railway restart

# 또는 수동 트리거
railway run python -c "from src.core.worker import Worker; Worker().process_one()"
```

#### Q2: LLM API 호출 실패
```bash
# 원인 확인
railway logs | grep "LLM"

# 해결: API 키 재설정
railway variables set ANTHROPIC_API_KEY=<새 키>
```

#### Q3: 데이터베이스 락
```bash
# 해결: 트랜잭션 타임아웃 증가
railway variables set DB_TIMEOUT=30

# 또는 WAL 모드 활성화
railway run sqlite3 data/sanjai.db "PRAGMA journal_mode=WAL;"
```

### 8.2 디버깅 팁

```bash
# 1. 상세 로깅 활성화
railway variables set LOG_LEVEL=DEBUG

# 2. 특정 모듈 로깅
railway variables set LOG_MODULES=engines.think,crawlers.precedent

# 3. 성능 프로파일링
railway run python -m cProfile -o profile.stats src/app.py

# 4. 메모리 프로파일링
railway run python -m memory_profiler src/app.py
```

---

## 9. 연락처

- **GitHub Issues**: https://github.com/sosobaeklaw-source/sanjai-insight/issues
- **프로젝트 관리자**: 대표님
- **기술 담당**: Claude Sonnet 4.5 (이 문서 작성자)

---

## 10. 부록

### 10.1 의존성 (requirements.txt)

```
anthropic>=0.18.0
openai>=1.12.0
python-telegram-bot>=20.7
pyyaml>=6.0
sqlite3  # built-in
redis>=5.0.0  # 선택
requests>=2.31.0
beautifulsoup4>=4.12.0
markdown>=3.5.0
```

### 10.2 환경변수 전체 목록

```bash
# 필수
TELEGRAM_BOT_TOKEN
ANTHROPIC_API_KEY
DATABASE_PATH
LOG_LEVEL
ENVIRONMENT
WORKER_COUNT
DAILY_COST_LIMIT
MONTHLY_COST_LIMIT

# 선택
OPENAI_API_KEY
REDIS_URL
VAULT_PATH
ALERT_THRESHOLD_ERROR
ALERT_THRESHOLD_WARNING
FCM_SERVER_KEY
APNS_KEY
DB_TIMEOUT
LOG_MODULES
```

### 10.3 성능 벤치마크 (예상)

| 작업 | 처리량 | 응답시간 | 비용 |
|------|--------|----------|------|
| 판례 크롤링 (100건) | 50건/분 | 120ms | $0.01 |
| LLM 분석 (1건) | 1건/10초 | 10s | $0.05 |
| 인사이트 생성 | 10건/분 | 6s | $0.50 |
| Telegram 푸시 | 100건/초 | 50ms | $0.00 |

---

**문서 끝**

> 이 문서는 sanjai-insight의 완전한 인수인계를 위해 작성되었습니다.
> 추가 질문이나 문제가 있으면 GitHub Issues에 등록해주세요.
