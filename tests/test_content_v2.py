"""Tests for enhanced content builder (Phase 6)."""
from __future__ import annotations

from src.insight_engine.content import build_draft, quality_check
from src.insight_engine.models import DraftDocument, InsightCandidate


def _make_insight(**overrides) -> InsightCandidate:
    defaults = dict(
        topic_id="industrial_accident",
        persona_focus="노동",
        headline="산업재해와 직업병 대응",
        why_now="최근 데이터에서 포착",
        key_points=["산재 신고 건수 15% 증가", "중대재해 처벌법 적용 사례 3건", "안전보건 관리체계 점검 필요"],
        evidence=["kosha_data", "moel_report"],
        score=5.0,
    )
    defaults.update(overrides)
    return InsightCandidate(**defaults)


def test_build_draft_has_5_sections():
    draft = build_draft("nomu", _make_insight())
    assert "데이터 팩트" in draft.body
    assert "해석" in draft.body
    assert "비유" in draft.body
    assert "체크리스트" in draft.body
    assert "다음 단계" in draft.body


def test_build_draft_nomu_persona():
    draft = build_draft("nomu", _make_insight())
    assert draft.persona == "nomu"
    assert draft.slug == "nomu_draft"
    assert "소백 노무사" in draft.title


def test_build_draft_lawyer_persona():
    draft = build_draft("lawyer", _make_insight(persona_focus="법률"))
    assert draft.persona == "lawyer"
    assert "소백 변호사" in draft.title


def test_build_draft_includes_evidence_footer():
    draft = build_draft("nomu", _make_insight())
    assert "kosha_data" in draft.body


def test_quality_check_pass():
    """With enough content, quality_check should detect sections."""
    draft = build_draft("nomu", _make_insight())
    checks = quality_check(draft)
    # Sections should be present
    assert not any("missing_section" in c for c in checks)


def test_quality_check_too_short():
    draft = DraftDocument(
        persona="nomu", slug="nomu_draft", title="Short",
        body="Too short", evidence=[], word_count=2, quality_checks=[],
    )
    checks = quality_check(draft)
    assert "too_short" in checks


def test_quality_check_missing_sections():
    draft = DraftDocument(
        persona="nomu", slug="nomu_draft", title="No sections",
        body="Just plain text without any structure at all. " * 50,
        evidence=[], word_count=100, quality_checks=[],
    )
    checks = quality_check(draft)
    assert any("missing_section" in c for c in checks)


def test_quality_check_insufficient_numbers():
    draft = DraftDocument(
        persona="nomu", slug="nomu_draft", title="No numbers",
        body="## 데이터 팩트\n\n## 해석\n\n## 비유\n\n## 체크리스트\n\nno numbers here at all. " * 30,
        evidence=[], word_count=100, quality_checks=[],
    )
    checks = quality_check(draft)
    assert "insufficient_numbers" in checks


def test_build_draft_quality_checks_populated():
    draft = build_draft("nomu", _make_insight())
    assert len(draft.quality_checks) > 0
    assert draft.quality_checks != []
