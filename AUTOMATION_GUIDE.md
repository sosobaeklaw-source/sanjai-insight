# 배포 및 검증 자동화 가이드

## 개요

sanjai-insight 프로젝트의 완전 자동화 배포 및 검증 시스템입니다.

## 목차

1. [배포 자동화](#1-배포-자동화)
2. [백업 검증](#2-백업-검증)
3. [모니터링 설정](#3-모니터링-설정)
4. [부하 테스트](#4-부하-테스트)
5. [프로토타입 자동화](#5-프로토타입-자동화)
6. [통합 테스트](#6-통합-테스트)
7. [성능 벤치마크](#7-성능-벤치마크)
8. [헬스 모니터링](#8-헬스-모니터링)

---

## 1. 배포 자동화

### 파일
- `scripts/railway_deploy_full.sh` (500줄)

### 기능
- Pre-flight 체크 (환경변수, Git 상태, 테스트)
- Blue-Green 배포 옵션
- 자동 Rollback
- Post-deployment 검증
- Slack/Telegram 알림

### 사용법

#### 표준 배포
```bash
./scripts/railway_deploy_full.sh
```

#### Blue-Green 배포
```bash
./scripts/railway_deploy_full.sh --blue-green
```

#### 알림 활성화
```bash
./scripts/railway_deploy_full.sh --notify
```

#### 테스트 스킵 (비권장)
```bash
./scripts/railway_deploy_full.sh --skip-tests
```

### Pre-flight 체크 항목
- [x] 필수 명령어 존재 (railway, git, curl, python3)
- [x] Railway 인증 상태
- [x] Railway 프로젝트 연결
- [x] Git 상태 (uncommitted/unpushed)
- [x] Railway 환경변수
- [x] 테스트 실행
- [x] 데이터베이스 백업

### Post-deployment 검증
- [x] Health check (10회 재시도, 5초 간격)
- [x] Status endpoint 확인
- [x] Metrics 수집
- [x] 로그 확인

### Rollback
배포 실패 시 자동으로 이전 커밋으로 롤백합니다.

```bash
# 수동 롤백
git checkout <commit_hash>
railway up -d
```

---

## 2. 백업 검증

### 파일
- `scripts/backup_verify.sh` (200줄)

### 기능
- 백업 파일 무결성 체크
- SQLite integrity check
- 복원 테스트 자동화
- S3 업로드 검증
- 일일 체크 리포트

### 사용법

#### 기본 검증
```bash
./scripts/backup_verify.sh
```

#### 복원 테스트
```bash
./scripts/backup_verify.sh --restore-test
```

#### S3 검증
```bash
./scripts/backup_verify.sh --s3-verify
```

#### 일일 리포트 생성
```bash
./scripts/backup_verify.sh --daily-report
```

### 검증 항목
- [x] 백업 파일 존재
- [x] 파일 크기 (0바이트 아님)
- [x] SQLite integrity check
- [x] 테이블 존재 확인
- [x] 인덱스 확인
- [x] 복원 가능 여부
- [x] S3 동기화 확인

### Cron 설정 (일일 자동 검증)
```bash
# crontab -e
0 2 * * * /path/to/scripts/backup_verify.sh --daily-report >> /var/log/backup_verify.log 2>&1
```

---

## 3. 모니터링 설정

### 파일
- `scripts/grafana_setup.sh` (150줄)

### 기능
- Grafana 대시보드 자동 임포트
- Prometheus data source 설정
- Alert contact point 설정 (Telegram)
- API key 기반 자동화

### 사용법

#### Grafana 설정
```bash
./scripts/grafana_setup.sh \
  --api-key YOUR_GRAFANA_API_KEY \
  --url http://grafana:3000 \
  --datasource-url http://sanjai-insight:8000/metrics
```

### 설정 항목
- [x] Prometheus data source
- [x] 대시보드 임포트 (`config/grafana_dashboard.json`)
- [x] Telegram contact point
- [x] Alert rules

### Grafana 대시보드 구성
- System Health (up metric)
- Request Rate (http_requests_total)
- Error Rate (5xx)
- Response Time (P50, P95, P99)
- Cost Tracking
- Worker Status

---

## 4. 부하 테스트

### 파일
- `tests/load_test.py` (400줄)

### 기능
- Locust 기반 부하 테스트
- 50건 인사이트 생성 시뮬레이션
- 성능 메트릭 수집
- 병목 지점 식별
- SLA 준수 체크

### 사용법

#### 웹 UI로 실행
```bash
locust -f tests/load_test.py --host=http://localhost:8000
# 브라우저에서 http://localhost:8089 접속
```

#### 헤드리스 모드
```bash
locust -f tests/load_test.py \
  --host=http://localhost:8000 \
  --users 10 \
  --spawn-rate 1 \
  --run-time 5m \
  --headless
```

#### 분산 부하 테스트
```bash
# Master
locust -f tests/load_test.py --master --expect-workers 4

# Workers (별도 터미널)
locust -f tests/load_test.py --worker --master-host localhost
```

### 시뮬레이션 시나리오
1. **Health Check** (빈도: 높음)
2. **Status Check** (빈도: 중간)
3. **Metrics Check** (빈도: 낮음)
4. **Watch Phase** (크롤링 시뮬레이션)
5. **Think Phase** (LLM 분석 시뮬레이션)
6. **Propose Phase** (Telegram 전송 시뮬레이션)
7. **Full Pipeline** (Watch → Think → Propose)

### SLA 기준
- P95 응답시간 < 5초
- P99 응답시간 < 10초
- 에러율 < 1%
- 처리량 > 1 req/sec

### 출력 리포트
- JSON 형식으로 `logs/load_test_report_*.json` 저장
- 병목 지점 자동 식별
- SLA 준수 여부

---

## 5. 프로토타입 자동화

### 파일
- `scripts/prototype_50_full.py` (600줄)

### 기능
- 50건 실제 케이스 시뮬레이션
- Watch → Think → Propose 전체 파이프라인
- 품질 메트릭 자동 수집
- Threshold 최적화 자동 제안
- 리포트 생성 (Text/HTML/JSON)

### 사용법

#### 기본 실행
```bash
python3 scripts/prototype_50_full.py
```

#### Dry-run (DB 저장 없이)
```bash
python3 scripts/prototype_50_full.py --dry-run
```

#### HTML 리포트 생성
```bash
python3 scripts/prototype_50_full.py --report html
```

#### 반복 횟수 변경
```bash
python3 scripts/prototype_50_full.py --iterations 100
```

### 수집 메트릭
- 크롤링 성공률
- 인사이트 생성 개수
- 신뢰도 분포 (평균, 최소, 최대)
- 승인율
- False Positive/Negative Rate
- 단계별 처리 시간 (Watch, Think, Propose)
- 비용 (총 비용, 승인 건당 비용)
- 품질 스코어 (0~100)

### Threshold 최적화 추천
스크립트는 다음 기준으로 임계값 조정을 자동 제안합니다:

- **승인율 < 50%** → 임계값 낮춤 (0.05)
- **승인율 > 85%** → 임계값 높임 (0.05)
- **False Positive > 10%** → 임계값 높임 (0.05)

### 출력
- Text 리포트: `reports/prototype_50_*.txt`
- HTML 리포트: `reports/prototype_50_*.html`
- JSON 메트릭: `reports/prototype_50_metrics_*.json`

---

## 6. 통합 테스트

### 파일
- `tests/integration/test_e2e_pipeline.py` (800줄)
- `tests/integration/test_api_integration.py`
- `tests/integration/test_telegram_integration.py`

### 기능
- E2E 파이프라인 테스트 (10개 케이스)
- API 통합 테스트
- Telegram 봇 통합 테스트
- 데이터 무결성 검증
- 트랜잭션 롤백 테스트
- 동시 처리 테스트

### 사용법

#### 전체 통합 테스트
```bash
pytest tests/integration/ -v
```

#### E2E 테스트만
```bash
pytest tests/integration/test_e2e_pipeline.py -v
```

#### API 테스트만
```bash
pytest tests/integration/test_api_integration.py -v
```

#### Telegram 테스트 (봇 토큰 필요)
```bash
export TELEGRAM_BOT_TOKEN=your_token
export TELEGRAM_CEO_CHAT_ID=your_chat_id
pytest tests/integration/test_telegram_integration.py -v
```

### 테스트 케이스

#### E2E Pipeline (10개)
- [x] TEST-E2E-001: 전체 파이프라인 성공
- [x] TEST-E2E-002: 낮은 신뢰도 필터링
- [x] TEST-E2E-003: 중복 방지
- [x] TEST-E2E-004: 승인 플로우
- [x] TEST-E2E-005: 에러 핸들링
- [x] TEST-E2E-006: 성능 베이스라인 (10건 < 5초)
- [x] TEST-E2E-007: 동시 처리
- [x] TEST-E2E-008: 데이터 무결성
- [x] TEST-E2E-009: 트랜잭션 롤백
- [x] TEST-E2E-010: 품질 임계값 강제

#### API Integration (6개)
- [x] TEST-API-001: /healthz
- [x] TEST-API-002: /status
- [x] TEST-API-003: /metrics
- [x] TEST-API-004: /cost
- [x] TEST-API-005: 응답 시간 (< 1초)
- [x] TEST-API-006: 동시 요청 (10개)

#### Telegram Integration (4개)
- [x] TEST-TELEGRAM-001: 메시지 전송
- [x] TEST-TELEGRAM-002: 버튼 포함 메시지
- [x] TEST-TELEGRAM-003: 콜백 데이터 파싱
- [x] TEST-TELEGRAM-004: 메시지 포맷팅

---

## 7. 성능 벤치마크

### 파일
- `scripts/benchmark.py` (300줄)

### 기능
- 응답 시간 측정 (P50, P95, P99)
- 비용 효율성 분석
- 품질 스코어 계산
- 히스토리 비교

### 사용법

#### 베이스라인 생성
```bash
python3 scripts/benchmark.py --baseline --version v2.0.0
```

#### 벤치마크 실행
```bash
python3 scripts/benchmark.py --version v2.1.0
```

#### 베이스라인과 비교
```bash
python3 scripts/benchmark.py \
  --version v2.1.0 \
  --compare benchmarks/baseline.json
```

### 출력
- Benchmark 결과: `benchmarks/benchmark_*.json`
- 베이스라인: `benchmarks/baseline.json`
- 비교 리포트: `benchmarks/comparison_*.json`

### 메트릭
- **성능**: Response Time (P50/P95/P99), Throughput, Error Rate
- **단계별**: Watch/Think/Propose 평균 처리 시간
- **비용**: 인사이트당/승인당 비용
- **품질**: Quality Score (0~100), Precision, Recall
- **리소스**: Memory, CPU

### 비교 예시
```
Benchmark Comparison Report
========================================
Baseline: 2026-03-03 10:00:00 (v2.0.0)
Current:  2026-03-03 15:00:00 (v2.1.0)

Improvements:
  ✓ response_time_p95_ms: +15.3%
  ✓ quality_score: +8.2%
  ✓ throughput_rps: +12.1%

Regressions:
  ✗ cost_per_approved_krw: -5.4%

Overall Delta: +7.5%
✓ Performance IMPROVED
========================================
```

---

## 8. 헬스 모니터링

### 파일
- `scripts/health_monitor.py` (400줄)

### 기능
- 24시간 무인 모니터링
- 자동 알림 (Critical만)
- Self-healing 시도
- 에스컬레이션 로직

### 사용법

#### 1회 체크
```bash
python3 scripts/health_monitor.py --once
```

#### 데몬 모드 (지속 실행)
```bash
python3 scripts/health_monitor.py --daemon
```

#### Systemd 서비스 등록
```bash
# /etc/systemd/system/sanjai-health-monitor.service
[Unit]
Description=sanjai-insight Health Monitor
After=network.target

[Service]
Type=simple
User=sanjai
WorkingDirectory=/path/to/sanjai-insight
ExecStart=/usr/bin/python3 scripts/health_monitor.py --daemon
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable sanjai-health-monitor
sudo systemctl start sanjai-health-monitor
sudo systemctl status sanjai-health-monitor
```

### 체크 항목

#### Database
- [x] DB 파일 존재
- [x] Integrity check
- [x] 필수 테이블 존재
- [x] DB 크기

#### API
- [x] /healthz 응답
- [x] /status 응답
- [x] 응답 시간

#### Worker
- [x] 최근 작업 개수 (1시간)
- [x] 실패율
- [x] 대기 작업 개수

#### Cost
- [x] 월간 예산 대비 사용률
- [x] 임계값 (90%, 100%)

### Self-Healing 전략

#### Database
- Integrity 실패 → 백업에서 복원 시도

#### API
- 응답 없음 → 재시작 시도

#### Worker
- 높은 실패율 → 실패 작업 재시도

### 알림 정책
- **INFO**: 로그만 (알림 없음)
- **WARNING**: 로그만 (알림 없음)
- **CRITICAL**: Telegram 알림 (5분 쿨다운)

### 로그
- 일일 로그: `logs/health_monitor_YYYYMMDD.log`
- 로테이션: 자동 (30일 보관)

---

## 무인 운영 체크리스트

### 배포 전 (Manual)
- [ ] `.env` 환경변수 설정
- [ ] Railway 프로젝트 연결
- [ ] Telegram 봇 설정
- [ ] 백업 스크립트 Cron 등록
- [ ] 헬스 모니터 Systemd 등록

### 배포 (Automated)
- [x] Pre-flight checks
- [x] 테스트 실행
- [x] 백업 생성
- [x] 배포 실행
- [x] Health check
- [x] Rollback (실패 시)

### 배포 후 (Automated)
- [x] 헬스 모니터링 (24/7)
- [x] 비용 추적
- [x] 백업 검증 (일일)
- [x] 성능 벤치마크 (주간)

### 주간 리뷰 (Manual)
- [ ] 배포 로그 확인
- [ ] 성능 트렌드 분석
- [ ] 비용 리뷰
- [ ] 프로토타입 결과 검토
- [ ] Threshold 조정

---

## 트러블슈팅

### 배포 실패
```bash
# 로그 확인
cat logs/deploy_*.log

# Rollback 상태 확인
git log --oneline -10

# Railway 로그 확인
railway logs --limit 100
```

### 백업 실패
```bash
# 수동 백업
bash scripts/backup.sh

# 백업 검증
bash scripts/backup_verify.sh --restore-test
```

### 헬스 체크 실패
```bash
# 수동 체크
python3 scripts/health_monitor.py --once

# DB 복구
bash scripts/restore.sh --latest
```

### 부하 테스트 실패
```bash
# Locust 로그 확인
cat logs/load_test_report_*.json

# API 로그 확인
railway logs | grep ERROR
```

---

## 연락처

문제 발생 시:
1. 로그 확인 (`logs/` 디렉토리)
2. Health check 실행
3. Telegram 알림 확인
4. 필요 시 수동 개입

**자동화 원칙**: Critical 이벤트만 알림, 나머지는 로그로 기록
