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


async def _require_api_server():
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            response = await client.get(f"{API_BASE_URL}/healthz")
            if response.status_code not in (200, 503):
                pytest.skip("local API server is not exposing the expected health endpoint")
    except httpx.HTTPError:
        pytest.skip("local API server is not running")


# ============================================================================
# API Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_api_healthz():
    """API-001: /healthz 엔드포인트"""
    await _require_api_server()
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE_URL}/healthz")
        assert response.status_code == 200
        assert response.text == "OK"


@pytest.mark.asyncio
async def test_api_status():
    """API-002: /status 엔드포인트"""
    await _require_api_server()
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE_URL}/status")
        assert response.status_code == 200
        data = response.json()

        assert "message" in data
        assert "correlation_id" not in data


@pytest.mark.asyncio
async def test_api_metrics():
    """API-003: /health 엔드포인트"""
    await _require_api_server()
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert "db_connected" in data
        assert "telegram_configured" in data


@pytest.mark.asyncio
async def test_api_cost():
    """API-004: /cost 엔드포인트"""
    await _require_api_server()
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE_URL}/cost")
        assert response.status_code == 200
        data = response.json()

        assert "message" in data
        assert "example" in data


@pytest.mark.asyncio
async def test_api_response_time():
    """API-005: 응답 시간 체크"""
    import time

    await _require_api_server()
    async with httpx.AsyncClient() as client:
        start = time.time()
        response = await client.get(f"{API_BASE_URL}/healthz")
        elapsed = time.time() - start

        assert response.status_code == 200
        assert elapsed < 1.0  # 1초 이내 응답


@pytest.mark.asyncio
async def test_api_concurrent_requests():
    """API-006: 동시 요청 처리"""
    await _require_api_server()
    async with httpx.AsyncClient() as client:
        tasks = [client.get(f"{API_BASE_URL}/healthz") for _ in range(10)]

        import asyncio
        responses = await asyncio.gather(*tasks)

        assert all(r.status_code == 200 for r in responses)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
