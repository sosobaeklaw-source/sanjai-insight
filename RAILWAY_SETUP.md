# Railway 배포 설정 가이드

## 1. Railway CLI 설정

```bash
# Railway 프로젝트 링크 (최초 1회)
cd "C:\Users\user\손원일\documents\sanjai-insight"
railway link
```

## 2. 환경변수 설정

Railway CLI 또는 웹 대시보드에서 다음 환경변수를 설정하세요:

### 2.1 CLI로 설정 (권장)

```bash
# 필수 환경변수
railway variables set TELEGRAM_BOT_TOKEN="<대표님 제공>"
railway variables set ANTHROPIC_API_KEY="<대표님 제공>"
railway variables set DATABASE_PATH="data/sanjai.db"
railway variables set LOG_LEVEL="INFO"
railway variables set ENVIRONMENT="production"
railway variables set WORKER_COUNT="4"
railway variables set DAILY_COST_LIMIT="10.0"
railway variables set MONTHLY_COST_LIMIT="300.0"

# 선택 환경변수
railway variables set OPENAI_API_KEY="<선택>"
railway variables set REDIS_URL="<선택>"
railway variables set VAULT_PATH="/vault/sanjai-vault"
```

### 2.2 웹 대시보드로 설정

1. https://railway.app/ 로그인
2. 프로젝트 선택
3. Variables 탭 이동
4. 다음 변수 추가:

| 변수명 | 값 | 필수 |
|--------|-----|------|
| TELEGRAM_BOT_TOKEN | <대표님 제공> | ✅ |
| ANTHROPIC_API_KEY | <대표님 제공> | ✅ |
| DATABASE_PATH | data/sanjai.db | ✅ |
| LOG_LEVEL | INFO | ✅ |
| ENVIRONMENT | production | ✅ |
| WORKER_COUNT | 4 | ✅ |
| DAILY_COST_LIMIT | 10.0 | ✅ |
| MONTHLY_COST_LIMIT | 300.0 | ✅ |
| OPENAI_API_KEY | <선택> | ⬜ |
| REDIS_URL | <선택> | ⬜ |

## 3. 배포 실행

```bash
# 배포
railway up --detach

# 로그 확인
railway logs

# 상태 확인
railway status
```

## 4. 배포 후 검증

```bash
# Health check
curl https://<your-app>.railway.app/healthz

# Status 확인
curl https://<your-app>.railway.app/health

# Cost 확인
curl https://<your-app>.railway.app/cost
```

## 5. 문제 해결

### Railway CLI 설치 확인

```bash
railway --version
```

없다면 설치:
```bash
npm install -g @railway/cli
# 또는
brew install railway
```

### 프로젝트 링크 확인

```bash
railway status
```

### 로그 실시간 확인

```bash
railway logs --follow
```

## 6. 참고

- 전체 가이드: HANDOFF.md Section 3
- Railway 공식 문서: https://docs.railway.app/
