"""Tests for enhanced Telegram notifications (Phase 8)."""
from __future__ import annotations

from unittest.mock import patch

from src.insight_engine.config import RuntimeConfig
from src.insight_engine.models import DraftDocument
from src.insight_engine.notify import (
    build_notification_message,
    notify_telegram,
    send_telegram,
)


def _make_config(tmp_path, token="", chat_id=""):
    return RuntimeConfig(
        repo_root=tmp_path,
        data_root=tmp_path / "data",
        published_root=tmp_path / "published",
        reports_root=tmp_path / "reports",
        env_source="test",
        doppler_project="sanjai-ai",
        doppler_config="prd",
        vault_path=None,
        secret_presence={},
        telegram_bot_token=token,
        boss_chat_id=chat_id,
    )


def _make_draft(persona="nomu"):
    return DraftDocument(
        persona=persona,
        slug=f"{persona}_draft",
        title=f"[Test] {persona} draft",
        body="Body",
        evidence=[],
        word_count=1,
        quality_checks=["pass"],
    )


def test_build_notification_message():
    drafts = [_make_draft("nomu"), _make_draft("lawyer")]
    msg = build_notification_message(drafts, "run-123")
    assert "run-123" in msg
    assert "초안 2건" in msg
    assert "nomu" in msg.lower() or "Test" in msg


def test_build_notification_with_wp_urls():
    drafts = [_make_draft("nomu")]
    wp_urls = {"nomu_draft": "https://example.com/draft/1"}
    msg = build_notification_message(drafts, "run-123", wp_urls=wp_urls)
    assert "https://example.com/draft/1" in msg


def test_notify_telegram_missing_config(tmp_path):
    config = _make_config(tmp_path)
    artifact = notify_telegram(config, [_make_draft()], "run-1", dry_run=False)
    assert artifact.status == "missing_config"


def test_notify_telegram_dry_run(tmp_path):
    config = _make_config(tmp_path, token="tok", chat_id="123")
    artifact = notify_telegram(config, [_make_draft()], "run-1", dry_run=True)
    assert artifact.status == "skipped_dry_run"
    assert "preview" in artifact.metadata


@patch("src.insight_engine.notify.httpx.post")
def test_send_telegram_success(mock_post):
    mock_resp = type("R", (), {
        "status_code": 200,
        "raise_for_status": lambda self: None,
        "json": lambda self: {"result": {"message_id": 42}},
    })()
    mock_post.return_value = mock_resp
    result = send_telegram("token", "123", "hello")
    assert result["message_id"] == 42


@patch("src.insight_engine.notify.httpx.post", side_effect=Exception("fail"))
def test_send_telegram_failure(mock_post):
    result = send_telegram("token", "123", "hello")
    assert result is None
