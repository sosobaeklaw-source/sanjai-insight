from __future__ import annotations

import json

from src.insight_engine.config import RuntimeConfig
from src.insight_engine.pipeline import PipelineOptions, PipelineRunner


def build_config(tmp_path):
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
        anthropic_api_key="",
        word_press_url="",
        word_press_site_url="",
        word_press_user="",
        word_press_app_password="",
        telegram_bot_token="",
        telegram_chat_id="",
        boss_chat_id="",
    )


def test_pipeline_runner_writes_local_artifacts(tmp_path):
    config = build_config(tmp_path)
    result = PipelineRunner(config, PipelineOptions(days=7, dry_run=True)).run()

    latest_report = config.reports_root / "health" / "pipeline_latest.json"
    manifest = next(config.published_root.rglob("manifest.json"))

    assert result.mode == "dry-run"
    assert latest_report.exists()
    assert manifest.exists()
    assert len(result.drafts) == 2
    payload = json.loads(latest_report.read_text(encoding="utf-8"))
    assert payload["run_id"] == result.run_id
    assert payload["drafts"][0]["persona"] == "nomu"
