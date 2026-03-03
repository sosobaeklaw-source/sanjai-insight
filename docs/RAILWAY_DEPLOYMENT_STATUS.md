# Railway Deployment Status Report

## 배포 정보
- **배포 시각**: 2026-03-04 02:26:00 (약 10분 전)
- **배포 URL**: https://sanjai-insight-production.up.railway.app
- **최신 커밋**: ad28a26 (docs: HANDOFF 신규 + CLAUDE.md Step 7 업데이트)
- **배포 방법**: `railway up` (로컬에서 실행)

## Health Check 결과

### 모니터링 기간
- **시작**: 2026-03-04 02:29:18
- **종료**: 2026-03-04 02:38:39
- **총 시도**: 15회 (30초 간격 10회 + 60초 간격 5회)
- **총 소요 시간**: 약 9분

### 모든 엔드포인트 실패

| 엔드포인트 | HTTP 상태 | 응답 메시지 | 응답 시간 |
|-----------|----------|------------|----------|
| `/` | 404 | Application not found | 0.14s |
| `/healthz` | 404 | Application not found | 0.11s |
| `/health` | 404 | Application not found | 0.26s |
| `/status` | 404 | Application not found | 0.10s |

### 에러 응답 예시
```json
{
  "status": "error",
  "code": 404,
  "message": "Application not found",
  "request_id": "ZBY35KpCQiy-A_BaDcO5xA"
}
```

## 원인 분석

### 1. Railway 배포 상태 불명
Railway의 "Application not found" 에러는 다음 중 하나를 의미:
- 빌드가 실패했거나 아직 완료되지 않음
- 서비스가 시작되지 않았거나 충돌함
- Railway 프로젝트 설정 오류 (도메인 매핑, 서비스 ID 등)

### 2. 로그 확인 불가
Railway API 키나 CLI 인증 없이는 다음을 확인할 수 없음:
- 빌드 로그 (Dockerfile 실행 상태)
- 서비스 로그 (uvicorn 시작 여부, 에러 메시지)
- 배포 상태 (BUILD QUEUED → BUILDING → DEPLOYING → RUNNING)
- 환경변수 설정 상태

### 3. 코드베이스는 정상
로컬 검증 결과 (2026-03-04 01:50):
- FastAPI 서버 정상 동작 확인 (`uvicorn src.server:app`)
- Health Check 엔드포인트 200 OK
- 의존성 설치 완료 (fastapi, uvicorn, psutil)
- Railway 설정 파일 정상 (railway.toml, Dockerfile)

## 설정 검토

### railway.toml
```toml
[build]
builder = "DOCKERFILE"

[deploy]
startCommand = "python -m uvicorn src.server:app --host 0.0.0.0 --port $PORT"
restartPolicyType = "ON_FAILURE"
```
- ✅ Dockerfile 빌더 지정
- ✅ uvicorn 시작 명령 정확
- ✅ PORT 환경변수 사용
- ✅ 재시작 정책 설정

### Dockerfile
```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y sqlite3
RUN useradd -m -u 1000 appuser && mkdir -p /app/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=appuser:appuser . .
USER appuser
CMD ["python", "-m", "src.app"]
```
- ✅ Python 3.12 베이스 이미지
- ✅ SQLite 설치
- ✅ Non-root 사용자
- ⚠️ CMD는 railway.toml의 startCommand로 덮어씀 (정상)

### requirements.txt (핵심 의존성)
```
fastapi==0.115.6
uvicorn==0.34.0
psutil==6.1.1
httpx==0.28.1
pydantic==2.10.5
python-telegram-bot==21.10
```
- ✅ 모든 의존성 명시적 버전 지정
- ✅ 로컬 설치 확인 완료

## 가능한 문제 시나리오

### 시나리오 1: 빌드 중 의존성 설치 실패
**확률**: 중간
**증상**: Railway가 Docker 이미지를 빌드하는 중 pip 설치 실패
**원인**:
- 특정 패키지의 바이너리 의존성 부족
- Python 3.12 호환성 문제
- 네트워크 타임아웃

**해결책**:
- Railway 대시보드에서 빌드 로그 확인
- Dockerfile에 추가 시스템 패키지 설치
- requirements.txt 버전 조정

### 시나리오 2: 환경변수 미설정
**확률**: 높음
**증상**: 서비스가 시작되지만 즉시 충돌
**원인**:
- `DB_PATH` 환경변수 누락 → 파일 생성 실패
- `PORT` 환경변수 누락 (Railway 자동 제공되지만 확인 필요)
- 기타 필수 환경변수 누락 (TELEGRAM_BOT_TOKEN은 선택적)

**해결책**:
- Railway 대시보드에서 환경변수 설정:
  - `DB_PATH=data/insight.db` (기본값 있지만 명시 권장)
  - `PORT` (Railway 자동 제공, 확인만)

### 시나리오 3: 파일 권한 문제
**확률**: 낮음
**증상**: SQLite DB 파일 생성 불가
**원인**:
- `/app/data` 디렉토리 쓰기 권한 부족
- Railway의 읽기 전용 파일 시스템

**해결책**:
- Dockerfile의 `RUN mkdir -p /app/data && chown -R appuser:appuser /app` 확인 (이미 구현됨)
- Railway Volume 마운트 추가 (영구 스토리지 필요 시)

### 시나리오 4: Railway 프로젝트 설정 오류
**확률**: 중간
**증상**: 배포는 성공했지만 도메인 라우팅 실패
**원인**:
- Railway 프로젝트가 올바른 Git 브랜치를 추적하지 않음
- 서비스 도메인 설정 오류
- Railway 프로젝트 ID와 URL 불일치

**해결책**:
- Railway 대시보드에서 프로젝트 설정 확인
- 배포 브랜치가 `master` 또는 `main`인지 확인
- 도메인 설정 재확인

### 시나리오 5: 배포 대기열 지연
**확률**: 높음
**증상**: 배포가 QUEUED 상태로 장시간 대기
**원인**:
- Railway 플랫폼 부하
- 무료/스타터 플랜의 낮은 우선순위
- 배포 슬롯 대기

**해결책**:
- 대기 (최대 15-30분)
- Railway 대시보드에서 배포 상태 확인
- 필요 시 수동 재배포 트리거

## 대표님 조치 필요 사항

### 즉시 조치 (우선순위 높음)
1. **Railway 대시보드 접속** (https://railway.app)
   - 프로젝트: `sanjai-insight-production`
   - 확인 사항:
     - 현재 배포 상태 (Queued/Building/Deploying/Running/Failed)
     - 빌드 로그 (에러 메시지)
     - 서비스 로그 (uvicorn 출력)

2. **환경변수 설정 확인**
   - Variables 탭에서 다음 변수 확인:
     ```
     DB_PATH=data/insight.db
     PORT=(자동 제공됨, 확인만)
     ```
   - 선택적 (봇 기능 필요 시):
     ```
     TELEGRAM_BOT_TOKEN=<토큰>
     OPENAI_API_KEY=<키>
     ANTHROPIC_API_KEY=<키>
     ```

3. **배포 상태 확인**
   - Deployments 탭에서 최신 배포 상태
   - 실패 시 에러 메시지 확인
   - 성공 시 서비스 URL이 활성화되었는지 확인

### 수동 재배포 (필요 시)
Railway 대시보드에서:
1. Deployments 탭 → 최신 배포 선택
2. "Redeploy" 버튼 클릭
3. 빌드 로그 실시간 확인

또는 CLI:
```bash
cd "C:/Users/user/손원일/documents/sanjai-insight"
railway up
```

### 로그 수집
다음 명령으로 로그 확인 (Railway CLI 필요):
```bash
railway logs
railway logs --build  # 빌드 로그만
```

## Health Check 재검증 절차

배포가 성공하면 다음 순서로 검증:

### 1. 기본 Health Check
```bash
curl https://sanjai-insight-production.up.railway.app/healthz
```
예상 응답: `OK` (200)

### 2. 상세 Health Status
```bash
curl https://sanjai-insight-production.up.railway.app/health | jq .
```
예상 응답:
```json
{
  "status": "healthy",
  "timestamp": "2026-03-04T02:40:00Z",
  "database": {
    "status": "ok",
    "path": "data/insight.db",
    "size_mb": 0.01
  },
  "system": {
    "memory_used_mb": 120,
    "disk_used_percent": 15
  }
}
```

### 3. Root Endpoint
```bash
curl https://sanjai-insight-production.up.railway.app/
```
예상 응답:
```json
{
  "service": "sanjai-insight",
  "version": "2.0.0",
  "status": "running",
  "timestamp": "2026-03-04T02:40:00Z"
}
```

### 4. 응답 시간 측정
```bash
curl -o /dev/null -s -w "Time: %{time_total}s\nHTTP: %{http_code}\n" \
  https://sanjai-insight-production.up.railway.app/healthz
```
예상: < 1초

## 다음 단계 (배포 성공 후)

### 1. Worker 프로세스 추가 배포 고려
현재는 FastAPI 웹 서버만 배포됨. Watch → Think → Propose 파이프라인 실행을 위해서는:
- Railway에 별도 Worker 서비스 추가, 또는
- 동일 서비스 내에서 백그라운드 Worker 실행 (gunicorn worker 방식)

### 2. 환경변수 완전성 체크
API 키 설정:
- `OPENAI_API_KEY`: Think 엔진용
- `ANTHROPIC_API_KEY`: Think 엔진용
- `TELEGRAM_BOT_TOKEN`: Propose 엔진 + Bot 핸들러용

### 3. 프로토타입 실행
```bash
python scripts/prototype_50.py
```
- 50개 문서 수집 + 인덱싱 + 인사이트 생성
- 운영 임계값 조정용 데이터 수집

### 4. 본 운영 전환
- 스케줄러 활성화 (매일 아침 6시)
- 모니터링 대시보드 연동
- 경보 설정 (에러율, 응답 시간)

## 문제 지속 시 백업 계획

### 옵션 A: Render 배포
Railway 대안:
- 유사한 PaaS (Dockerfile 지원)
- 무료 플랜 제공
- 더 간단한 설정

### 옵션 B: VPS 직접 배포
Ubuntu 서버에서:
```bash
docker build -t sanjai-insight .
docker run -d -p 8000:8000 \
  -e DB_PATH=data/insight.db \
  -v $(pwd)/data:/app/data \
  sanjai-insight
```

### 옵션 C: 로컬 개발 모드 유지
배포 없이 로컬에서:
```bash
python -m uvicorn src.server:app --host 0.0.0.0 --port 8000
```
- ngrok으로 외부 접근 가능
- 개발/테스트용으로 충분

## 요약

### 현재 상태
- ❌ Railway 배포: 실패 또는 진행 중 (9분 경과, 응답 없음)
- ✅ 코드베이스: 정상 (로컬 검증 완료)
- ✅ 설정 파일: 정상 (railway.toml, Dockerfile, requirements.txt)
- ❌ Health Check: 모든 엔드포인트 404

### 블로커
1. Railway 대시보드 접근 불가 (로그 확인 불가)
2. 배포 상태 불명 (빌드 실패? 시작 실패? 대기 중?)
3. 에러 메시지 부족 ("Application not found"만)

### 권장 조치
1. 대표님이 Railway 대시보드에서 배포 상태 + 로그 확인
2. 환경변수 설정 확인 (`DB_PATH` 등)
3. 필요 시 수동 재배포
4. 성공 시 이 문서의 "Health Check 재검증 절차" 실행

### 타임라인
- **2026-03-04 02:26**: 배포 실행
- **2026-03-04 02:29**: 첫 Health Check 시도 (실패)
- **2026-03-04 02:38**: 마지막 Health Check 시도 (실패, 15회)
- **2026-03-04 02:40**: 이 보고서 작성

---

**작성자**: Claude Code Agent
**작성일시**: 2026-03-04 02:40:00
**문서 버전**: 1.0
