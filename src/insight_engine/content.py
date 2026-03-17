from __future__ import annotations

import re

from .models import DraftDocument, InsightCandidate


PERSONA_META = {
    "nomu": {
        "name": "소백 노무사",
        "slug": "nomu_draft",
        "angle": "근로자와 사업주가 실제로 무엇을 점검해야 하는지",
        "cta": "현장에서 바로 점검이 필요하면 노무 상담으로 연결하세요.",
    },
    "lawyer": {
        "name": "소백 변호사",
        "slug": "lawyer_draft",
        "angle": "법률상 책임과 분쟁 대응 구조가 어떻게 달라지는지",
        "cta": "분쟁이 이미 시작됐다면 증거를 정리한 뒤 법률 상담으로 이어가세요.",
    },
}


def _render_paragraphs(persona: str, insight: InsightCandidate) -> list[str]:
    """Render insight into 5-section structured draft."""
    meta = PERSONA_META[persona]
    lines: list[str] = []

    # --- Section 1: Data Facts ---
    lines.append("## \U0001f4ca 데이터 팩트")
    lines.append("")
    for point in insight.key_points:
        lines.append(f"- {point}")
    lines.append("")

    # --- Section 2: Interpretation ---
    lines.append("## \U0001f50d 해석")
    lines.append("")
    lines.append(
        f"{meta['name']}의 시선으로 보면 핵심은 {meta['angle']}입니다."
    )
    lines.append(
        f"이번 {insight.headline} 이슈가 시사하는 공통점은 "
        "규정 변화와 실무 대응 사이의 간극이 커지고 있다는 점입니다."
    )
    lines.append(
        "법령 문구를 아는 것만으로는 부족하고 "
        "실제 절차와 증빙 흐름까지 함께 점검해야 합니다."
    )
    lines.append("")

    # --- Section 3: Simple Analogy ---
    lines.append("## \U0001f4a1 비유")
    lines.append("")
    lines.append(
        "건물 소방 점검에 비유하면 이해가 쉽습니다. "
        "소화기가 있다고 안전한 게 아니라, "
        "유효기간을 확인하고 위치를 모두가 알아야 실제 화재에서 쓸 수 있습니다."
    )
    lines.append(
        "마찬가지로 내부 규정이 존재한다고 끝이 아니라, "
        "최신 기준에 맞는지, 담당자가 실제로 운용할 수 있는지까지 확인해야 합니다."
    )
    lines.append("")

    # --- Section 4: Action Checklist ---
    lines.append("## \u2705 체크리스트")
    lines.append("")
    lines.append(
        "1. 현재 적용 중인 내부 문서와 실제 운영 관행이 일치하는지 확인하기"
    )
    lines.append(
        "2. 최근 개정 또는 최근 사례와 충돌하는 부분이 없는지 표시하기"
    )
    lines.append(
        "3. 외부 설명이 필요한 경우 쟁점별 근거 문서를 따로 묶어두기"
    )
    lines.append(
        "4. 담당자 변경이나 인수인계가 생겨도 같은 설명이 유지되도록 문장 정리하기"
    )
    lines.append(
        "5. 분쟁 발생 시 30일 이내 초기 대응 타임라인을 미리 수립하기"
    )
    lines.append("")

    # --- Section 5: CTA ---
    lines.append("## \U0001f4de 다음 단계")
    lines.append("")
    lines.append(meta["cta"])
    lines.append("")

    # --- Evidence footer ---
    if insight.evidence:
        lines.append("---")
        lines.append("")
        lines.append("검토에 사용한 근거 경로:")
        for evidence in insight.evidence:
            lines.append(f"- {evidence}")

    return lines


def quality_check(draft: DraftDocument) -> list[str]:
    """Check draft quality: length 1500-2500 chars, sections exist, numbers>=3, avg sentence<=50 chars."""
    issues: list[str] = []
    char_count = len(draft.body)
    if char_count < 1500:
        issues.append("too_short")
    if char_count > 2500:
        issues.append("too_long")

    required_sections = ["데이터 팩트", "해석", "비유", "체크리스트"]
    for section in required_sections:
        if section not in draft.body:
            issues.append(f"missing_section_{section}")

    numbers = re.findall(r"\d+", draft.body)
    if len(numbers) < 3:
        issues.append("insufficient_numbers")

    sentences = [s.strip() for s in re.split(r"[.!?。]\s*", draft.body) if s.strip()]
    if sentences:
        avg_len = sum(len(s) for s in sentences) / len(sentences)
        if avg_len > 50:
            issues.append("sentences_too_long")

    return issues or ["pass"]


def build_draft(persona: str, insight: InsightCandidate) -> DraftDocument:
    meta = PERSONA_META[persona]
    title = f"[{meta['name']}] {insight.headline}"
    body = "\n".join(_render_paragraphs(persona, insight))

    draft = DraftDocument(
        persona=persona,
        slug=meta["slug"],
        title=title,
        body=body,
        evidence=list(insight.evidence),
        word_count=len(body.split()),
        quality_checks=[],
    )

    draft.quality_checks = quality_check(draft)

    return draft
