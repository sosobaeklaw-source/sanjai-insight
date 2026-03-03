# Railway 배포 Health Check 보고서

## 배포 정보
- **프로젝트**: sanjai-insight
- **배포 URL**: https://sanjai-insight-production.up.railway.app
- **환경**: production
- **검증일**: 2026-03-04
- **상태**: 빌드 대기 중 → 웹 서버 추가 후 재배포 필요

## 문제 진단

### 초기 배포 문제 (2026-03-04 00:00 KST)
모든 엔드포인트에서 404 "Application not found" 오류 발생:
- `/healthz` → 404
- `/health` → 404
- `/status` → 404
- `/cost` → 404
- `/` → 404
- `/docs` → 404

**원인 분석**:
1. `src/app.py`는 Worker 기반 백그라운드 서비스 (비 웹서버)
2. `src/api/` 모듈에 health check 함수들은 존재하나 HTTP 엔드포인트 없음
3. Railway는 HTTP 웹 서버를 기대하지만 Worker만 실행 중
4. `railway.toml` startCommand가 `python -m src.app` (Worker 실행)

### 해결 방안 적용

#### 1. FastAPI 웹 서버 생성
- **파일**: `src/server.py` (신규 생성, 79줄)
- **기능**:
  - `/` - 서비스 정보
  - `/healthz` - Railway liveness check (200/503)
  - `/health` - 상세 health status (DB, Telegram, Vault 확인)
  - `/status?correlation_id=xxx` - 실행 상태 조회
  - `/cost?correlation_id=xxx` - 비용 분석

#### 2. 의존성 추가
`requirements.txt` 업데이트:
```
fastapi>=0.115.0
uvicorn>=0.32.0
psutil>=6.1.0
```

#### 3. Railway 시작 명령 변경
`railway.toml` 수정:
```toml
[deploy]
startCommand = "python -m uvicorn src.server:app --host 0.0.0.0 --port $PORT"
```

#### 4. 로컬 검증 완료
```
$ python -c "asyncio.run(get_healthz('data/insight.db'))"
Status: 200, Message: OK
```

## 다음 단계

### 재배포 필요
1. 변경사항 커밋 + Push
2. Railway 자동 재배포 트리거
3. Health Check 재검증:
   ```bash
   curl https://sanjai-insight-production.up.railway.app/healthz
   # Expected: "OK" (200)

   curl https://sanjai-insight-production.up.railway.app/health
   # Expected: JSON health status
   ```

### 환경변수 설정 (Railway Dashboard)
- `DB_PATH`: `data/insight.db`
- `TELEGRAM_BOT_TOKEN`: (대표님 제공 필요)
- `ANTHROPIC_API_KEY`: (대표님 제공 필요)
- `GEMINI_API_KEY`: (대표님 제공 필요)
- `VAULT_PATH`: `/data/vault`
- `MAX_COST_USD`: `5.0`
- `MAX_TIME_SEC`: `3600`
- `PORT`: (Railway 자동 설정)

### 검증 체크리스트
- [ ] Railway 재배포 완료
- [ ] `/healthz` → 200 OK
- [ ] `/health` → JSON with db_connected=true
- [ ] `/` → 서비스 정보 반환
- [ ] Database 영구 볼륨 마운트 확인
- [ ] 환경변수 설정 (API 키)
- [ ] Worker 프로세스 별도 실행 (선택적)

## 아키텍처 노트

### 현재 구조
```
Railway 배포 = FastAPI 웹 서버 (src/server.py)
  ├── Health Check 엔드포인트 (운영 모니터링)
  ├── Status/Cost API (조회 전용)
  └── Database: data/insight.db (읽기 전용)

Worker 프로세스 (src/app.py) = 별도 실행 필요
  ├── Watch/Think/Propose/Diagnose 엔진
  ├── Job Queue 처리
  └── Database: data/insight.db (읽기/쓰기)
```

### 권장 운영 모드
1. **Web Server (Railway)**: 모니터링 + 조회 API만 제공
2. **Worker (별도 서버)**: 실제 인사이트 생성 작업 실행
3. **공유 Database**: Railway 영구 볼륨 또는 외부 DB

또는:

1. **Railway 단일 배포**: Web Server + Worker 동시 실행 (Docker CMD 변경)
   ```dockerfile
   CMD ["sh", "-c", "python -m uvicorn src.server:app --host 0.0.0.0 --port $PORT & python -m src.app"]
   ```

## 검증 결과 (재배포 후 업데이트 예정)

### 엔드포인트 테스트
| Endpoint | Status | Response Time | 비고 |
|----------|--------|---------------|------|
| `/` | - | - | 재배포 대기 |
| `/healthz` | - | - | 재배포 대기 |
| `/health` | - | - | 재배포 대기 |
| `/status` | - | - | 재배포 대기 |
| `/cost` | - | - | 재배포 대기 |

### Health Status 상세
```json
TBD (재배포 후 업데이트)
```

## 참고 문서
- CLAUDE.md Step 7: 운영 전환
- DEPLOYMENT_SUCCESS.md: Railway 배포 가이드
- src/api/health.py: Health check 로직
