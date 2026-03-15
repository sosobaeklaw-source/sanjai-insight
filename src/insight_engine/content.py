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
            "현장에서 문제가 커지는 방식은 늘 비슷합니다. 초기에는 '예전처럼 해도 되겠지' 하고 넘기지만, 분쟁이 시작되면 최근 기준을 확인하지 않은 흔적이 바로 드러납니다.",
            "그래서 이번 주제는 단순한 정보 소개가 아니라, 현재 시점의 업무 기준을 다시 맞추는 기준점으로 읽어야 합니다.",
            "",
            "실무적으로는 다음 순서가 안전합니다.",
            "1. 내 사안이 어느 법률 영역에 걸치는지 먼저 분류합니다.",
            "2. 최근 지침·판례·행정자료 중 무엇이 직접 영향을 주는지 확인합니다.",
            "3. 증빙자료를 바로 확보하고, 설명 가능한 타임라인으로 정리합니다.",
            "4. 내부 담당자와 외부 전문가의 역할을 나눠서 대응합니다.",
            "5. 공개 설명이 필요한 사안인지, 조용히 정리해야 하는 사안인지 초기에 선을 긋습니다.",
            "",
            "독자가 가장 많이 놓치는 부분은 '문제가 생긴 뒤에 자료를 찾는다'는 점입니다.",
            "이번 주제는 사후 대응보다 사전 점검의 가치가 훨씬 큽니다.",
            "그래서 현업 기준으로는 체크리스트를 미리 두고 반복 점검하는 편이 비용과 시간을 동시에 줄입니다.",
            "특히 노무·법률 이슈는 한 번 방향을 잘못 잡으면 해명 비용이 계속 쌓입니다.",
            "초기 대응 문장, 내부 보고 표현, 상대방에게 보내는 첫 안내문이 모두 나중의 증거가 되기 때문입니다.",
            "",
            "이번 이슈를 읽을 때는 두 가지 질문을 같이 가져가면 좋습니다.",
            "첫째, 지금 보이는 변화가 우리 조직의 계약서·지침·실무 프로세스에 바로 영향을 주는가입니다.",
            "둘째, 실제 분쟁이 발생했을 때 그 영향을 설명할 자료를 이미 갖고 있는가입니다.",
            "이 두 질문에 자신 있게 답하지 못하면, 이미 점검 우선순위가 높은 상태라고 보는 편이 맞습니다.",
            "",
            f"{meta['name']} 관점에서 특히 강조하고 싶은 부분도 있습니다.",
            "실무자는 보통 하나의 법률 조항만 보고 결론을 내리지만, 실제 사건은 자료의 흐름과 대응의 일관성까지 함께 봅니다.",
            "따라서 이번처럼 자료가 여러 갈래에서 모일 때는 개별 자료를 따로 보지 말고 하나의 설명 구조로 묶어야 합니다.",
            "그 구조가 있어야 상담 단계에서도 핵심 쟁점이 흔들리지 않고, 이후 검토나 발행 단계에서도 메시지가 안정됩니다.",
            "",
            "이번 초안은 실제 법률 자문이나 노무 자문을 대체하지 않습니다.",
            "다만 어떤 쟁점이 커지고 있는지, 지금 무엇을 먼저 챙겨야 하는지 빠르게 이해하는 데 목적이 있습니다.",
            "독자가 이 글을 읽고 바로 실행할 수 있어야 한다는 점도 중요합니다.",
            "그래서 용어를 줄이고, 행동 순서와 확인 포인트를 먼저 제시하는 방식으로 정리했습니다.",
            "현장에서는 긴 설명보다 '오늘 안에 무엇을 확인해야 하는가'가 더 중요하기 때문입니다.",
            "",
            "실행 관점에서 권하는 최소 체크리스트는 다음과 같습니다.",
            "- 현재 적용 중인 내부 문서와 실제 운영 관행이 일치하는지 확인하기",
            "- 최근 개정 또는 최근 사례와 충돌하는 부분이 없는지 표시하기",
            "- 외부 설명이 필요한 경우 쟁점별 근거 문서를 따로 묶어두기",
            "- 담당자 변경이나 인수인계가 생겨도 같은 설명이 유지되도록 문장 정리하기",
            "",
            "이 정도만 해도 분쟁 예방 효과가 상당히 큽니다.",
            "반대로 이 단계가 빠지면, 사안이 커졌을 때 사실관계보다 설명의 혼선이 더 큰 리스크로 돌아옵니다.",
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
