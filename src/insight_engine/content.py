from __future__ import annotations

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
    meta = PERSONA_META[persona]
    lines = [
        f"{insight.headline}은 지금 바로 현장에서 설명이 필요한 주제입니다.",
        f"{meta['name']}의 시선으로 보면 핵심은 {meta['angle']}입니다.",
        "이번 초안은 최근 수집 자료를 바탕으로, 독자가 바로 이해하고 점검할 수 있게 정리했습니다.",
        "",
        "먼저 사실관계를 짚겠습니다.",
    ]
    for point in insight.key_points:
        lines.append(f"- {point}")
    lines.extend(
        [
            "",
            "이 자료들이 시사하는 공통점은 규정 변화와 실무 대응 사이의 간극이 커지고 있다는 점입니다.",
            "즉, 법령 문구를 아는 것만으로는 부족하고 실제 절차와 증빙 흐름까지 함께 점검해야 합니다.",
            "",
            "실무적으로는 다음 순서가 안전합니다.",
            "1. 내 사안이 어느 법률 영역에 걸치는지 먼저 분류합니다.",
            "2. 최근 지침·판례·행정자료 중 무엇이 직접 영향을 주는지 확인합니다.",
            "3. 증빙자료를 바로 확보하고, 설명 가능한 타임라인으로 정리합니다.",
            "",
            "독자가 가장 많이 놓치는 부분은 '문제가 생긴 뒤에 자료를 찾는다'는 점입니다.",
            "이번 주제는 사후 대응보다 사전 점검의 가치가 훨씬 큽니다.",
            "그래서 현업 기준으로는 체크리스트를 미리 두고 반복 점검하는 편이 비용과 시간을 동시에 줄입니다.",
            "",
            "이번 초안은 실제 법률 자문이나 노무 자문을 대체하지 않습니다.",
            "다만 어떤 쟁점이 커지고 있는지, 지금 무엇을 먼저 챙겨야 하는지 빠르게 이해하는 데 목적이 있습니다.",
            meta["cta"],
        ]
    )
    if insight.evidence:
        lines.extend(["", "검토에 사용한 근거 경로:"])
        for evidence in insight.evidence:
            lines.append(f"- {evidence}")
    return lines


def build_draft(persona: str, insight: InsightCandidate) -> DraftDocument:
    meta = PERSONA_META[persona]
    title = f"[{meta['name']}] {insight.headline}"
    body = "\n".join(_render_paragraphs(persona, insight))
    quality_checks = []
    char_count = len(body)
    if char_count < 1200:
        quality_checks.append("too_short")
    if char_count > 4000:
        quality_checks.append("too_long")
    if "사건번호" in body:
        quality_checks.append("manual_case_verification_required")
    return DraftDocument(
        persona=persona,
        slug=meta["slug"],
        title=title,
        body=body,
        evidence=list(insight.evidence),
        word_count=len(body.split()),
        quality_checks=quality_checks or ["pass"],
    )
