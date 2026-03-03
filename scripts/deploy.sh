#!/bin/bash
# ============================================================================
# Simple Deploy Script (Legacy)
# ============================================================================
# 용도: 간단한 Railway 배포 (테스트 포함)
# 권장: 프로덕션 배포는 scripts/railway_deploy.sh 사용
# ============================================================================

set -e
echo "Deploying sanjai-insight..."

# Run tests (optional - skip with SKIP_TESTS=1)
if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
    echo "Running tests..."
    pytest tests/ -v --tb=short
else
    echo "Skipping tests (SKIP_TESTS=1)"
fi

# Deploy to Railway
echo "Deploying to Railway..."
railway up -d

echo "Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Check logs: railway logs"
echo "2. Health check: ./scripts/health_check.sh https://YOUR_DOMAIN"
