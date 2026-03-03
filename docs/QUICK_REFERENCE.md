# Railway 배포 - 대표님 조치 Quick Reference

## 현재 상태
- ❌ **배포 미완료** (Application Not Found)
- ⏰ **배포 시각**: 2026-03-04 02:26
- 🔍 **모니터링**: 9분, 15회 시도, 모두 404
- 📍 **URL**: https://sanjai-insight-production.up.railway.app

---

## 즉시 확인 사항 (5분 소요)

### 1. Railway 대시보드 접속
https://railway.app → `sanjai-insight-production` 프로젝트

### 2. 배포 상태 확인
**Deployments** 탭 → 최신 배포 클릭

| 상태 | 조치 |
|------|------|
| `QUEUED` | 대기 (최대 30분) |
| `BUILDING` | Build Logs 확인 |
| `FAILED` | Logs 확인 후 재배포 |
| `RUNNING` | Service URL 재확인 |

### 3. 로그 확인
- **Build Logs**: `pip install` 에러 확인
- **Service Logs**: `uvicorn` 시작 메시지 확인

### 4. 환경변수 확인 (선택적)
**Variables** 탭:
- `DB_PATH=data/insight.db` (권장)
- `PORT` (자동 제공, 확인만)

---

## 문제 발견 시

### 빌드 실패
→ Build Logs 에러 메시지 → 재배포

### 시작 실패
→ Service Logs 에러 메시지 → 환경변수 설정 → 재배포

### 재배포 방법
Railway 대시보드: **Redeploy** 버튼
또는 CLI: `railway up`

---

## 배포 성공 확인

```bash
curl https://sanjai-insight-production.up.railway.app/healthz
```
예상: `OK` (200)

```bash
curl https://sanjai-insight-production.up.railway.app/health | jq .
```
예상: `{"status":"healthy", ...}`

---

## 상세 문서

1. **RAILWAY_MONITORING_SUMMARY.md** (요약)
2. **RAILWAY_DEPLOYMENT_STATUS.md** (상세 분석)
3. **MONITORING_SESSION.md** (타임라인)

---

**작성**: 2026-03-04 02:42
**다음 조치**: Railway 대시보드 확인 필요
