"""Tests for insight engine monitor (Phase 11)."""
from __future__ import annotations

import json

from src.insight_engine.config import RuntimeConfig
from src.insight_engine.monitor import (
    check_api_keys,
    check_collectors,
    check_vault,
    check_wp,
    daily_report,
)


def _make_config(tmp_path, vault=True):
    vault_path = None
    if vault:
        vault_path = tmp_path / "vault"
        vault_path.mkdir()
        (vault_path / "test.md").write_text("# Test", encoding="utf-8")
    return RuntimeConfig(
        repo_root=tmp_path,
        data_root=tmp_path / "data",
        published_root=tmp_path / "published",
        reports_root=tmp_path / "reports",
        env_source="test",
        doppler_project="sanjai-ai",
        doppler_config="prd",
        vault_path=vault_path,
        secret_presence={},
    )


def test_check_collectors_no_keys(monkeypatch):
    for key in ("DATA_GO_KR_API_KEY", "DART_API", "KOSIS_API", "ECOS_API", "LAW_API_OC", "BRAVE_API_KEY", "NAVER_CLIENT_ID", "GOOGLE_CSE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    result = check_collectors()
    assert all(v == "missing" for v in result.values())


def test_check_collectors_with_keys(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_API_KEY", "key")
    monkeypatch.setenv("DART_API", "key")
    result = check_collectors()
    assert result["kosha"] == "ok"
    assert result["dart"] == "ok"


def test_check_vault_ok(tmp_path):
    config = _make_config(tmp_path, vault=True)
    result = check_vault(config)
    assert result["status"] == "ok"
    assert result["markdown_files"] == 1


def test_check_vault_not_configured(tmp_path):
    config = _make_config(tmp_path, vault=False)
    result = check_vault(config)
    assert result["status"] == "not_configured"


def test_check_wp_not_configured(tmp_path):
    config = _make_config(tmp_path)
    result = check_wp(config)
    assert result["status"] == "not_configured"


def test_check_api_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    result = check_api_keys()
    assert result["anthropic"] == "present"


def test_daily_report(tmp_path, monkeypatch):
    for key in ("DATA_GO_KR_API_KEY", "DART_API", "KOSIS_API", "ECOS_API", "LAW_API_OC"):
        monkeypatch.delenv(key, raising=False)
    config = _make_config(tmp_path, vault=True)
    report = daily_report(config)
    assert "timestamp" in report
    assert "collectors" in report
    assert "vault" in report
    assert "summary" in report
    assert report["vault"]["status"] == "ok"


def test_daily_report_with_pipeline_report(tmp_path, monkeypatch):
    config = _make_config(tmp_path)
    health_dir = config.reports_root / "health"
    health_dir.mkdir(parents=True)
    (health_dir / "pipeline_latest.json").write_text(
        json.dumps({"run_id": "test-run", "mode": "dry-run", "source_records": [1, 2], "drafts": [1], "warnings": []}),
        encoding="utf-8",
    )
    report = daily_report(config)
    assert report["last_pipeline"]["run_id"] == "test-run"
    assert report["last_pipeline"]["source_count"] == 2
