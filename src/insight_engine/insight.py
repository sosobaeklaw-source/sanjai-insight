from __future__ import annotations

import re
from collections import defaultdict

from .models import InsightCandidate, SourceRecord


TOPIC_RULES = {
    "산재": ("industrial_accident", "노동", "산업재해와 직업병 대응"),
    "중대재해": ("serious_accident", "법률", "중대재해 리스크와 대응"),
    "임금": ("wage", "노동", "임금체불과 근로시간 쟁점"),
    "해고": ("dismissal", "노동", "해고·징계 분쟁 대응"),
    "괴롭힘": ("harassment", "노동", "직장 내 괴롭힘 대응"),
    "개인정보": ("privacy", "법률", "개인정보 유출과 책임"),
    "계약": ("contract", "법률", "계약분쟁과 손해배상"),
    "부동산": ("real_estate", "법률", "부동산·임대차 쟁점"),
}


def _extract_tokens(text: str) -> list[str]:
    return re.findall(r"[가-힣A-Za-z0-9]{2,}", text)


def extract_insights(records: list[SourceRecord]) -> list[InsightCandidate]:
    grouped: dict[str, dict[str, object]] = defaultdict(
        lambda: {"score": 0.0, "evidence": [], "points": [], "focus": "법률", "headline": ""}
    )

    for record in records:
        text = f"{record.title} {record.excerpt}"
        matched = False
        for keyword, (topic_id, focus, headline) in TOPIC_RULES.items():
            if keyword in text:
                matched = True
                entry = grouped[topic_id]
                entry["score"] = float(entry["score"]) + (2.0 if record.status == "collected" else 0.5)
                entry["focus"] = focus
                entry["headline"] = headline
                entry["evidence"] = list(dict.fromkeys([*entry["evidence"], *record.evidence]))
                tokens = [token for token in _extract_tokens(record.excerpt) if len(token) >= 3][:3]
                point = record.title if not tokens else f"{record.title}: {', '.join(tokens)}"
                entry["points"] = [*entry["points"], point]
        if not matched and record.status == "collected":
            entry = grouped["regulatory_shift"]
            entry["score"] = float(entry["score"]) + 1.0
            entry["focus"] = "법률"
            entry["headline"] = "최근 지침과 판례 변화"
            entry["evidence"] = list(dict.fromkeys([*entry["evidence"], *record.evidence]))
            entry["points"] = [*entry["points"], record.title]

    candidates: list[InsightCandidate] = []
    for topic_id, data in grouped.items():
        if not data["evidence"]:
            continue
        points = list(dict.fromkeys(data["points"]))[:4]
        candidates.append(
            InsightCandidate(
                topic_id=topic_id,
                persona_focus=str(data["focus"]),
                headline=str(data["headline"]),
                why_now="최근 자료와 설정된 데이터 소스에서 반복적으로 포착된 주제입니다.",
                key_points=points,
                evidence=list(data["evidence"])[:6],
                score=float(data["score"]),
            )
        )

    if not candidates:
        candidates.append(
            InsightCandidate(
                topic_id="baseline_update",
                persona_focus="노동",
                headline="이번 주 노동·법률 실무 체크포인트",
                why_now="사용 가능한 자료가 제한적이어서 기본 주제 패킷으로 대체했습니다.",
                key_points=["Vault 또는 공공데이터 연결 상태를 먼저 점검하세요."],
                evidence=[],
                score=0.1,
            )
        )

    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[:4]
