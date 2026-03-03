#!/usr/bin/env python3
"""
API 통합 테스트
===============
"""

import pytest
import httpx
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ============================================================================
# Test Configuration
# ============================================================================

API_BASE_URL = "http://localhost:8000"


# ============================================================================
# API Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_api_healthz():
    """API-001: /healthz 엔드포인트"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE_URL}/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_api_status():
    """API-002: /status 엔드포인트"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE_URL}/status")
        assert response.status_code == 200
        data = response.json()

        # 필수 필드 체크
        assert "status" in data
        assert "uptime_seconds" in data
        assert "pending_jobs" in data


@pytest.mark.asyncio
async def test_api_metrics():
    """API-003: /metrics 엔드포인트"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE_URL}/metrics")
        assert response.status_code == 200

        # Prometheus 형식 체크
        text = response.text
        assert "# HELP" in text or "# TYPE" in text


@pytest.mark.asyncio
async def test_api_cost():
    """API-004: /cost 엔드포인트"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE_URL}/cost")
        assert response.status_code == 200
        data = response.json()

        assert "monthly_budget_krw" in data
        assert "current_spend_krw" in data


@pytest.mark.asyncio
async def test_api_response_time():
    """API-005: 응답 시간 체크"""
    import time

    async with httpx.AsyncClient() as client:
        start = time.time()
        response = await client.get(f"{API_BASE_URL}/healthz")
        elapsed = time.time() - start

        assert response.status_code == 200
        assert elapsed < 1.0  # 1초 이내 응답


@pytest.mark.asyncio
async def test_api_concurrent_requests():
    """API-006: 동시 요청 처리"""
    async with httpx.AsyncClient() as client:
        tasks = [client.get(f"{API_BASE_URL}/healthz") for _ in range(10)]

        import asyncio
        responses = await asyncio.gather(*tasks)

        assert all(r.status_code == 200 for r in responses)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
