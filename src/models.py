"""
sanjai-insight Data Models
Pydantic v2 models for type safety and validation
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# ========== Enums ==========


class SourceType(str, Enum):
    SUPREME_COURT = "SUPREME_COURT"
    HIGH_COURT = "HIGH_COURT"
    KCOMWEL = "KCOMWEL"
    MOEL = "MOEL"
    NAVER_TREND = "NAVER_TREND"
    COMPETITOR = "COMPETITOR"


class DataType(str, Enum):
    PRECEDENT = "PRECEDENT"
    POLICY = "POLICY"
    TREND = "TREND"
    COMPETITOR_POST = "COMPETITOR_POST"


class CrawledDataStatus(str, Enum):
    NEW = "NEW"
    INDEXED = "INDEXED"
    ANALYZED = "ANALYZED"
    ARCHIVED = "ARCHIVED"


class CrawledBy(str, Enum):
    RAILWAY = "RAILWAY"
    OPENCLAW = "OPENCLAW"


class DocumentCategory(str, Enum):
    PRECEDENT = "PRECEDENT"
    LAW = "LAW"
    CASE_DOC = "CASE_DOC"
    BRIEF = "BRIEF"
    RESEARCH = "RESEARCH"
    MARKETING = "MARKETING"
    OPS = "OPS"


class DocumentSourceType(str, Enum):
    VAULT = "VAULT"
    CRAWLED = "CRAWLED"


class InsightType(str, Enum):
    CASE_IMPACT = "CASE_IMPACT"
    MARKET_OPPORTUNITY = "MARKET_OPPORTUNITY"
    STRATEGY_SHIFT = "STRATEGY_SHIFT"


class Urgency(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class InsightStatus(str, Enum):
    NEW = "NEW"
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ProposalResponse(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


class ContentType(str, Enum):
    BLOG = "BLOG"
    SNS = "SNS"
    NEWSLETTER = "NEWSLETTER"


class ContentStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"


class WatchLogStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


# ========== Base Models ==========


class BaseRecord(BaseModel):
    """Base model for all records with UUID"""

    id: str = Field(default_factory=lambda: str(uuid4()))

    model_config = {"from_attributes": True}


# ========== Domain Models ==========


class CrawledData(BaseRecord):
    """수집 원본 데이터"""

    source: SourceType
    crawled_at: datetime = Field(default_factory=datetime.now)
    data_type: DataType
    raw_content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: CrawledDataStatus = CrawledDataStatus.NEW
    crawled_by: CrawledBy = CrawledBy.RAILWAY
    created_at: datetime = Field(default_factory=datetime.now)


class IndexedDocument(BaseRecord):
    """구조화된 인덱스 문서"""

    crawled_data_id: Optional[str] = None
    source_type: DocumentSourceType
    category: DocumentCategory
    subcategory: Optional[str] = None
    title: str
    date: Optional[datetime] = None
    keywords: list[str] = Field(default_factory=list)
    entities: dict[str, Any] = Field(default_factory=dict)
    summary: str
    embedding_id: Optional[str] = None
    indexed_at: datetime = Field(default_factory=datetime.now)


class Insight(BaseRecord):
    """인사이트"""

    type: InsightType
    trigger_data_ids: list[str]
    title: str
    body: dict[str, Any]  # 프레임별 구조화
    confidence: float = Field(ge=0.0, le=1.0)
    urgency: Urgency
    suggested_actions: list[str] = Field(default_factory=list)
    affected_cases: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    status: InsightStatus = InsightStatus.NEW
    model_used: Optional[str] = None
    tokens_used: int = 0

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v


class Proposal(BaseRecord):
    """제안"""

    insight_id: str
    message_text: str
    proposed_at: datetime = Field(default_factory=datetime.now)
    response: ProposalResponse = ProposalResponse.PENDING
    response_at: Optional[datetime] = None
    response_detail: Optional[str] = None
    executed_action: Optional[str] = None
    feedback: Optional[str] = None
    response_latency_sec: Optional[int] = None


class MarketingContent(BaseRecord):
    """마케팅 콘텐츠"""

    insight_id: Optional[str] = None
    content_type: ContentType
    title: str
    target_keyword: Optional[str] = None
    seo_meta: dict[str, Any] = Field(default_factory=dict)
    draft: str
    legal_review: dict[str, Any] = Field(default_factory=dict)
    status: ContentStatus = ContentStatus.DRAFT
    published_url: Optional[str] = None
    performance: dict[str, Any] = Field(default_factory=dict)
    total_cost: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)


class TrendSnapshot(BaseRecord):
    """트렌드 스냅샷"""

    keyword: str
    period: str
    search_volume: Optional[int] = None
    change_percent: Optional[float] = None
    related_keywords: list[str] = Field(default_factory=list)
    captured_at: datetime = Field(default_factory=datetime.now)


class WatchLog(BaseRecord):
    """크롤링 실행 로그"""

    source: SourceType
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: WatchLogStatus
    items_collected: int = 0
    error_message: Optional[str] = None


class SystemMetrics(BaseRecord):
    """시스템 메트릭 (v2 신규)"""

    date: str  # YYYY-MM-DD
    total_insights: int = 0
    high_confidence_ratio: float = 0.0
    acceptance_rate: float = 0.0
    avg_response_latency_sec: float = 0.0
    total_cost_krw: float = 0.0
    crawler_uptime_ratio: float = 0.0
    top_rejection_reasons: dict[str, int] = Field(default_factory=dict)


class PromptVersion(BaseRecord):
    """프롬프트 버전 관리 (v2 신규)"""

    engine: str  # think, propose, marketing
    version: int
    prompt_text: str
    performance_score: Optional[float] = None
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)


class CostLog(BaseRecord):
    """비용 로그 (v2 신규)"""

    timestamp: datetime = Field(default_factory=datetime.now)
    module: str  # think, marketing_ma, marketing_mb, etc.
    model: str
    input_tokens: int
    output_tokens: int
    cost_krw: float
    insight_id: Optional[str] = None


# ========== Helper Models ==========


class CaseInfo(BaseModel):
    """sanjai-agent의 사건 정보 (AgentBridge용)"""

    case_id: str
    case_name: str
    status: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseDetail(BaseModel):
    """sanjai-agent의 상세 사건 정보"""

    case_id: str
    case_name: str
    status: str
    phases: list[str]
    documents: list[dict[str, Any]]
    runlog: list[dict[str, Any]]


class SearchResult(BaseModel):
    """벡터DB 검색 결과"""

    doc_id: str
    content: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphResult(BaseModel):
    """지식그래프 검색 결과"""

    entity_id: str
    entity_type: str
    properties: dict[str, Any]
    relationships: list[dict[str, Any]] = Field(default_factory=list)


class RunlogStats(BaseModel):
    """RUNLOG 통계"""

    case_id: Optional[str] = None
    total_runs: int
    avg_duration_sec: float
    success_rate: float
    last_run: Optional[datetime] = None


class PipelineRequest(BaseModel):
    """sanjai-agent 파이프라인 요청"""

    action: str  # "generate_brief", "analyze_case", etc.
    case_id: str
    params: dict[str, Any] = Field(default_factory=dict)


class DiagnosisReport(BaseModel):
    """자기진단 보고서 (v2 신규)"""

    period: str
    acceptance_rate: float
    cost_total_krw: float
    cost_per_insight_krw: float
    crawler_uptime: float
    top_rejection_reasons: list[tuple[str, int]]
    auto_adjustments: list[str]
    pending_suggestions: list[str]
