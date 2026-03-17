"""Tests for real HTTP collectors (Phase 2)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.insight_engine.collectors import (
    CanonicalCollector,
    _fetch,
    _save_raw,
    collect_brave,
    collect_dart,
    collect_data_go_kr,
    collect_ecos,
    collect_google_cse,
    collect_kosha,
    collect_kosis,
    collect_law,
    collect_moel,
    collect_naver,
)
from src.insight_engine.config import RuntimeConfig


class FakeResponse:
    def __init__(self, data: dict, status_code: int = 200):
        self._data = data
        self.status_code = status_code
        self.url = MagicMock(host="test.example.com")

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


# ----------- _fetch tests -----------

@patch("src.insight_engine.collectors.httpx.get")
def test_fetch_success(mock_get):
    mock_get.return_value = FakeResponse({"ok": True})
    resp = _fetch("https://example.com/api")
    assert resp is not None
    assert resp.json() == {"ok": True}


@patch("src.insight_engine.collectors.httpx.get", side_effect=Exception("timeout"))
def test_fetch_retries_and_returns_none(mock_get):
    resp = _fetch("https://example.com/api", retries=2)
    assert resp is None
    assert mock_get.call_count == 2


# ----------- _save_raw tests -----------

def test_save_raw(tmp_path):
    _save_raw({"key": "value"}, "test_source", tmp_path)
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    data_path = tmp_path / "raw" / "test_source" / today / "data.json"
    manifest_path = tmp_path / "raw" / "test_source" / today / "manifest.json"
    assert data_path.exists()
    assert manifest_path.exists()
    assert json.loads(data_path.read_text())["key"] == "value"


# ----------- collect_kosha -----------

@patch("src.insight_engine.collectors._fetch")
def test_collect_kosha_with_key(mock_fetch, monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_API_KEY", "test-key")
    mock_fetch.return_value = FakeResponse({
        "response": {"body": {"items": {"item": [
            {"kindNm": "사망", "occurYear": "2025"},
        ]}}}
    })
    records = collect_kosha()
    assert len(records) == 1
    assert records[0].source == "kosha"
    assert records[0].status == "collected"


def test_collect_kosha_no_key(monkeypatch):
    monkeypatch.delenv("DATA_GO_KR_API_KEY", raising=False)
    assert collect_kosha() == []


# ----------- collect_moel -----------

@patch("src.insight_engine.collectors._fetch")
def test_collect_moel_with_key(mock_fetch, monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_API_KEY", "test-key")
    mock_fetch.return_value = FakeResponse({
        "response": {"body": {"items": {"item": [
            {"empNm": "고용현황", "baseDt": "2025-01"},
        ]}}}
    })
    records = collect_moel()
    assert len(records) == 1
    assert records[0].source == "moel"


# ----------- collect_dart -----------

@patch("src.insight_engine.collectors._fetch")
def test_collect_dart(mock_fetch, monkeypatch):
    monkeypatch.setenv("DART_API", "test-key")
    mock_fetch.return_value = FakeResponse({
        "list": [{"report_nm": "주요보고", "corp_name": "테스트사", "rcept_no": "123"}]
    })
    records = collect_dart()
    assert len(records) == 1
    assert records[0].source == "dart"
    assert "테스트사" in records[0].excerpt


# ----------- collect_kosis -----------

@patch("src.insight_engine.collectors._fetch")
def test_collect_kosis(mock_fetch, monkeypatch):
    monkeypatch.setenv("KOSIS_API", "test-key")
    mock_fetch.return_value = FakeResponse([{"TBL_NM": "인구통계"}])
    records = collect_kosis()
    assert len(records) == 1
    assert records[0].source == "kosis"


# ----------- collect_ecos -----------

@patch("src.insight_engine.collectors._fetch")
def test_collect_ecos(mock_fetch, monkeypatch):
    monkeypatch.setenv("ECOS_API", "test-key")
    mock_fetch.return_value = FakeResponse({
        "StatisticSearch": {"row": [
            {"STAT_NAME": "통화", "DATA_VALUE": "100", "TIME": "2025M01", "ITEM_NAME1": "M2"}
        ]}
    })
    records = collect_ecos()
    assert len(records) == 1
    assert records[0].source == "ecos"


# ----------- collect_law -----------

@patch("src.insight_engine.collectors._fetch")
def test_collect_law(mock_fetch, monkeypatch):
    monkeypatch.setenv("LAW_API_OC", "test-key")
    mock_fetch.return_value = FakeResponse({
        "LawSearch": {"law": [{"법령명한글": "근로기준법", "법령일련번호": "001"}]}
    })
    records = collect_law()
    assert len(records) == 1
    assert records[0].source == "law"


# ----------- collect_data_go_kr -----------

@patch("src.insight_engine.collectors._fetch")
def test_collect_data_go_kr(mock_fetch, monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_API_KEY", "test-key")
    mock_fetch.return_value = FakeResponse({
        "response": {"body": {"items": {"item": [
            {"jobNm": "노동시장", "baseDt": "2025-01"},
        ]}}}
    })
    records = collect_data_go_kr()
    assert len(records) == 1
    assert records[0].source == "data_go_kr"


# ----------- collect_brave -----------

@patch("src.insight_engine.collectors._fetch")
def test_collect_brave(mock_fetch, monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    mock_fetch.return_value = FakeResponse({
        "web": {"results": [
            {"title": "산업재해 뉴스", "description": "최근 산재 현황", "url": "https://example.com/1"}
        ]}
    })
    records = collect_brave()
    assert len(records) == 1
    assert records[0].source == "brave"
    assert records[0].url == "https://example.com/1"


# ----------- collect_naver -----------

@patch("src.insight_engine.collectors._fetch")
def test_collect_naver(mock_fetch, monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "secret")
    mock_fetch.return_value = FakeResponse({
        "items": [
            {"title": "<b>중대재해</b> 뉴스", "description": "설명", "originallink": "https://news.com/1", "pubDate": "2025-01-01"}
        ]
    })
    records = collect_naver()
    assert len(records) == 1
    assert records[0].source == "naver"
    assert "<b>" not in records[0].title


# ----------- collect_google_cse -----------

@patch("src.insight_engine.collectors._fetch")
def test_collect_google_cse(mock_fetch, monkeypatch):
    monkeypatch.setenv("GOOGLE_CSE_API_KEY", "key")
    monkeypatch.setenv("GOOGLE_CSE_ID", "cx")
    mock_fetch.return_value = FakeResponse({
        "items": [
            {"title": "노동법 판례", "snippet": "최신 판례 요약", "link": "https://example.com/2"}
        ]
    })
    records = collect_google_cse()
    assert len(records) == 1
    assert records[0].source == "google_cse"


def test_collect_google_cse_no_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_CSE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert collect_google_cse() == []


# ----------- CanonicalCollector integration -----------

def test_canonical_collector_calls_real_collectors(tmp_path, monkeypatch):
    """CanonicalCollector.collect() runs without errors even with no API keys."""
    # Clear all API keys
    for key in ("DATA_GO_KR_API_KEY", "DART_API", "KOSIS_API", "ECOS_API",
                "LAW_API_OC", "BRAVE_API_KEY", "NAVER_CLIENT_ID", "GOOGLE_CSE_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    vault = tmp_path / "vault"
    vault.mkdir()
    config = RuntimeConfig(
        repo_root=tmp_path,
        data_root=tmp_path / "data",
        published_root=tmp_path / "published",
        reports_root=tmp_path / "reports",
        env_source="test",
        doppler_project="sanjai-ai",
        doppler_config="prd",
        vault_path=vault,
        secret_presence={},
    )
    collector = CanonicalCollector(config)
    records = collector.collect(days=7)
    # Should have at least inventory and optional target records
    assert len(records) >= 3
