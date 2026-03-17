"""Tests for enhanced WordPress publishing (Phase 7)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.insight_engine.config import RuntimeConfig
from src.insight_engine.models import DraftDocument
from src.insight_engine.publishers import (
    _ensure_wp_url,
    publish_local,
    publish_wordpress,
)


def _make_config(tmp_path, wp_url="", wp_user="", wp_pass=""):
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
        word_press_url=wp_url,
        word_press_user=wp_user,
        word_press_app_password=wp_pass,
    )


def _make_draft(persona="nomu"):
    return DraftDocument(
        persona=persona,
        slug=f"{persona}_draft",
        title=f"[Test] {persona} draft",
        body="Test body content",
        evidence=["test_ev"],
        word_count=3,
        quality_checks=["pass"],
    )


def test_ensure_wp_url_bare_domain():
    assert _ensure_wp_url("example.com") == "https://example.com/wp-json/wp/v2/posts"


def test_ensure_wp_url_with_protocol():
    assert _ensure_wp_url("https://example.com") == "https://example.com/wp-json/wp/v2/posts"


def test_ensure_wp_url_already_correct():
    url = "https://example.com/wp-json/wp/v2/posts"
    assert _ensure_wp_url(url) == url


def test_publish_wordpress_missing_config(tmp_path):
    config = _make_config(tmp_path)
    artifacts = publish_wordpress(config, [_make_draft()], dry_run=False)
    assert len(artifacts) == 1
    assert artifacts[0].status == "missing_config"


def test_publish_wordpress_dry_run(tmp_path):
    config = _make_config(tmp_path, wp_url="https://ex.com", wp_user="u", wp_pass="p")
    artifacts = publish_wordpress(config, [_make_draft()], dry_run=True)
    assert all(a.status == "skipped_dry_run" for a in artifacts)


def test_publish_wordpress_fallback_on_error(tmp_path):
    config = _make_config(tmp_path, wp_url="https://ex.com", wp_user="u", wp_pass="p")
    with patch("src.insight_engine.publishers.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = Exception("connection error")
        mock_client_cls.return_value = mock_client

        artifacts = publish_wordpress(
            config, [_make_draft()], dry_run=False,
            output_root=tmp_path / "published", run_id="test-run",
        )
        # Should have fallback local artifacts + error artifact
        assert any(a.status == "error_fallback_local" for a in artifacts)


def test_publish_local(tmp_path):
    drafts = [_make_draft("nomu"), _make_draft("lawyer")]
    artifacts = publish_local(drafts, tmp_path / "published", "test-run")
    assert len(artifacts) == 3  # 2 drafts + 1 manifest
    assert all(a.status == "published" for a in artifacts)
