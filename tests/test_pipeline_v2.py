"""Tests for integrated pipeline (Phase 9)."""
from __future__ import annotations

import json

from src.insight_engine.config import RuntimeConfig
from src.insight_engine.pipeline import PipelineOptions, PipelineRunner


def _build_config(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("# 산업재해 체크\n\n산재와 중대재해 이슈 정리", encoding="utf-8")
    return RuntimeConfig(
        repo_root=tmp_path,
        data_root=tmp_path / "data",
        published_root=tmp_path / "published",
        reports_root=tmp_path / "reports",
        env_source="test",
        doppler_project="sanjai-ai",
        doppler_config="prd",
        vault_path=vault,
        secret_presence={
            "dart": True,
            "data_go_kr": True,
            "kosis": True,
            "ecos": True,
            "law_api_key": True,
            "brave": False,
            "naver_client_id": False,
            "google_cse_api_key": False,
            "vault": True,
        },
    )


def test_pipeline_dry_run(tmp_path):
    config = _build_config(tmp_path)
    result = PipelineRunner(config, PipelineOptions(days=7, dry_run=True)).run()
    assert result.mode == "dry-run"
    assert len(result.drafts) == 2
    assert result.drafts[0].persona == "nomu"
    assert result.drafts[1].persona == "lawyer"


def test_pipeline_writes_reports(tmp_path):
    config = _build_config(tmp_path)
    result = PipelineRunner(config, PipelineOptions(days=7)).run()
    report_path = config.reports_root / "health" / "pipeline_latest.json"
    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == result.run_id
    assert len(payload["drafts"]) == 2


def test_pipeline_local_artifacts(tmp_path):
    config = _build_config(tmp_path)
    result = PipelineRunner(config, PipelineOptions(days=7)).run()
    local_arts = [a for a in result.artifacts if a.target == "local_markdown"]
    assert len(local_arts) == 2


def test_pipeline_quality_checks_populated(tmp_path):
    config = _build_config(tmp_path)
    result = PipelineRunner(config, PipelineOptions(days=7)).run()
    for draft in result.drafts:
        assert len(draft.quality_checks) > 0


def test_pipeline_warnings(tmp_path):
    config = _build_config(tmp_path)
    result = PipelineRunner(config, PipelineOptions(days=7)).run()
    # WordPress and Telegram not configured
    assert "wordpress_draft_fallback_only" in result.warnings
    assert "telegram_preview_only" in result.warnings


def test_pipeline_with_wordpress_dry_run(tmp_path):
    config = _build_config(tmp_path)
    config.word_press_url = "https://example.com"
    config.word_press_user = "user"
    config.word_press_app_password = "pass"
    result = PipelineRunner(
        config, PipelineOptions(days=7, dry_run=True, publish_wordpress=True)
    ).run()
    wp_arts = [a for a in result.artifacts if a.target == "wordpress"]
    assert len(wp_arts) >= 1
    assert all(a.status == "skipped_dry_run" for a in wp_arts)


def test_pipeline_with_telegram_dry_run(tmp_path):
    config = _build_config(tmp_path)
    config.telegram_bot_token = "token"
    config.boss_chat_id = "123"
    result = PipelineRunner(
        config, PipelineOptions(days=7, dry_run=True, notify_telegram=True)
    ).run()
    tg_arts = [a for a in result.artifacts if a.target == "telegram"]
    assert len(tg_arts) == 1
    assert tg_arts[0].status == "skipped_dry_run"
