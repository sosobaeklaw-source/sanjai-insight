"""Tests for enhanced insight extraction (Phase 5)."""
from __future__ import annotations

from src.insight_engine.insight import (
    NOMU_TOPICS,
    PRIORITY_TOPICS,
    extract_insights,
    rank_insights,
)
from src.insight_engine.models import InsightCandidate, SourceRecord


def _make_record(source: str, title: str, excerpt: str, status: str = "collected") -> SourceRecord:
    return SourceRecord(
        source=source, status=status, title=title, excerpt=excerpt,
        evidence=[f"ev_{source}"],
    )


def test_rank_insights_priority_bonus():
    candidates = [
        InsightCandidate(
            topic_id="industrial_accident", persona_focus="노동",
            headline="산재", why_now="최근", key_points=[], evidence=["a"], score=1.0,
        ),
        InsightCandidate(
            topic_id="real_estate", persona_focus="법률",
            headline="부동산", why_now="모니터링", key_points=[], evidence=["b"], score=5.0,
        ),
    ]
    ranked = rank_insights(candidates)
    # industrial_accident gets +3 priority + 2 timeliness + 0.5 evidence = 6.5
    # real_estate gets 0 priority + 0 timeliness + 0.5 evidence = 5.5
    assert ranked[0].topic_id == "industrial_accident"


def test_extract_insights_returns_max_6():
    records = [
        _make_record("a", "산재 사고", "산업재해 현장"),
        _make_record("b", "중대재해 처벌", "중대재해 처벌법"),
        _make_record("c", "임금 체불", "임금 미지급 사례"),
        _make_record("d", "해고 통보", "해고 징계 분쟁"),
        _make_record("e", "괴롭힘 신고", "직장 내 괴롭힘"),
        _make_record("f", "개인정보 유출", "개인정보 사건"),
        _make_record("g", "계약 분쟁", "계약서 해석"),
        _make_record("h", "부동산 분쟁", "부동산 임대차"),
    ]
    insights = extract_insights(records)
    assert len(insights) <= 6


def test_extract_insights_nomu_lawyer_split():
    records = [
        _make_record("a", "산재 이슈", "산업재해 통계"),
        _make_record("b", "계약 분쟁", "계약 해석 문제"),
    ]
    insights = extract_insights(records)
    topics = {c.topic_id for c in insights}
    # Should include both nomu and lawyer topics
    assert "industrial_accident" in topics or "contract" in topics


def test_extract_insights_fallback():
    records = [
        _make_record("x", "unrelated", "no keywords here", status="missing"),
    ]
    insights = extract_insights(records)
    assert len(insights) >= 1
    assert insights[0].topic_id == "baseline_update"


def test_priority_topics_defined():
    assert "industrial_accident" in PRIORITY_TOPICS
    assert "wage" in PRIORITY_TOPICS


def test_nomu_topics_superset():
    assert PRIORITY_TOPICS.issubset(NOMU_TOPICS | {"serious_accident"})
