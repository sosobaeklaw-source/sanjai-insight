"""
Pytest configuration and fixtures
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import Database


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_db(tmp_path):
    """Create temporary test database"""
    db_path = tmp_path / "test.db"
    db = Database(str(db_path))

    # Initialize with both schemas
    schema_path = Path(__file__).parent.parent / "schema.sql"
    schema_v2_path = Path(__file__).parent.parent / "schema_v2_operational.sql"
    await db.init_db(str(schema_path))
    await db.init_db(str(schema_v2_path))

    yield db

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables"""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
    monkeypatch.setenv("TELEGRAM_CEO_CHAT_ID", "123456789")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")
    monkeypatch.setenv("GOOGLE_API_KEY", "test_google_key")
    monkeypatch.setenv("NAVER_CLIENT_ID", "test_naver_id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test_naver_secret")
