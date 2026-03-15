from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class SourceRecord:
    source: str
    status: str
    title: str
    excerpt: str = ""
    url: str | None = None
    published_at: str | None = None
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InsightCandidate:
    topic_id: str
    persona_focus: str
    headline: str
    why_now: str
    key_points: list[str]
    evidence: list[str]
    score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DraftDocument:
    persona: str
    slug: str
    title: str
    body: str
    evidence: list[str]
    word_count: int
    quality_checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PublishArtifact:
    target: str
    mode: str
    location: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PipelineResult:
    run_id: str
    mode: str
    env_source: str
    source_records: list[SourceRecord]
    insights: list[InsightCandidate]
    drafts: list[DraftDocument]
    artifacts: list[PublishArtifact]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "env_source": self.env_source,
            "source_records": [item.to_dict() for item in self.source_records],
            "insights": [item.to_dict() for item in self.insights],
            "drafts": [item.to_dict() for item in self.drafts],
            "artifacts": [item.to_dict() for item in self.artifacts],
            "warnings": list(self.warnings),
        }
