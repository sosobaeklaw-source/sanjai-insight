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


# ========== Operational Models (v2.0 운영화) ==========


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TERMINATED = "TERMINATED"


class EventType(str, Enum):
    WATCH_START = "WATCH_START"
    WATCH_END = "WATCH_END"
    ITEM_COLLECTED = "ITEM_COLLECTED"
    INDEX_START = "INDEX_START"
    INDEX_END = "INDEX_END"
    THINK_START = "THINK_START"
    THINK_END = "THINK_END"
    INSIGHT_CREATED = "INSIGHT_CREATED"
    INSIGHT_REJECTED = "INSIGHT_REJECTED"
    PROPOSE_START = "PROPOSE_START"
    PROPOSE_END = "PROPOSE_END"
    PROPOSAL_SENT = "PROPOSAL_SENT"
    APPROVAL_RECEIVED = "APPROVAL_RECEIVED"
    ACTION_EXECUTED = "ACTION_EXECUTED"
    DIAGNOSE_START = "DIAGNOSE_START"
    DIAGNOSE_END = "DIAGNOSE_END"
    AUTO_FIX_APPLIED = "AUTO_FIX_APPLIED"
    ERROR = "ERROR"
    TERMINATION = "TERMINATION"


class ApprovalDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    DEFER = "DEFER"
    DRAFT_ONLY = "DRAFT_ONLY"


class ValidationStatus(str, Enum):
    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"


class TelegramUpdate(BaseRecord):
    """Telegram 업데이트 (멱등성)"""

    update_id: int
    chat_id: int
    payload_json: dict[str, Any]
    processed_at: datetime = Field(default_factory=datetime.now)


class Job(BaseRecord):
    """스케줄 작업"""

    job_id: str = Field(default_factory=lambda: str(uuid4()))
    job_key: str  # 멱등 키
    type: str  # WATCH, THINK, PROPOSE, MARKETING
    payload_json: dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_error: Optional[str] = None


class RunLog(BaseRecord):
    """실행 로그"""

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    correlation_id: str
    job_id: Optional[str] = None
    status: RunStatus
    started_at: datetime
    ended_at: Optional[datetime] = None
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    meta_json: dict[str, Any] = Field(default_factory=dict)


class Checkpoint(BaseModel):
    """체크포인트"""

    correlation_id: str
    last_stage: str
    ctx_json: dict[str, Any]
    updated_at: datetime = Field(default_factory=datetime.now)


class Event(BaseRecord):
    """이벤트 (append-only)"""

    ts: datetime = Field(default_factory=datetime.now)
    type: EventType
    correlation_id: str
    payload_json: dict[str, Any]


class LLMCall(BaseRecord):
    """LLM 호출 로그"""

    correlation_id: str
    run_id: Optional[str] = None
    stage: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: Optional[int] = None
    cost_usd: float
    meta_json: dict[str, Any] = Field(default_factory=dict)


class VaultFile(BaseRecord):
    """볼트 파일 (증분 인덱싱)"""

    file_id: str = Field(default_factory=lambda: str(uuid4()))
    path: str
    sha256: str
    mtime: str
    size: int
    title: Optional[str] = None
    category: Optional[str] = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    indexed_at: datetime = Field(default_factory=datetime.now)


class VaultChunk(BaseRecord):
    """볼트 청크"""

    chunk_id: str = Field(default_factory=lambda: str(uuid4()))
    file_id: str
    start_line: int
    end_line: int
    text: str
    sha256: str


class Source(BaseRecord):
    """외부 수집 소스"""

    source_id: str = Field(default_factory=lambda: str(uuid4()))
    type: str
    base_url: Optional[str] = None
    config_json: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    last_success_at: Optional[datetime] = None
    last_error: Optional[str] = None


class SourceItem(BaseRecord):
    """수집 아이템"""

    item_id: str = Field(default_factory=lambda: str(uuid4()))
    source_id: str
    external_key: str  # 외부 시스템 ID (멱등)
    fetched_at: datetime
    payload_json: dict[str, Any]
    content_hash: str


class Evidence(BaseRecord):
    """근거"""

    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    correlation_id: str
    source_type: str  # VAULT, CRAWLED, SOURCE_ITEM
    locator_json: dict[str, Any]  # 위치 정보
    snippet: str  # 근거 텍스트 (최대 500자)
    content_hash: str


class InsightClaim(BaseRecord):
    """인사이트 주장 (claim-evidence 바인딩)"""

    claim_id: str = Field(default_factory=lambda: str(uuid4()))
    insight_id: str
    text: str
    evidence_ids_json: list[str]  # 최소 1개 필수


class ProposalAction(BaseRecord):
    """제안 액션"""

    proposal_id: str
    action_type: str
    action_payload_json: dict[str, Any]
    requires_approval: bool = True
    executed: bool = False
    executed_at: Optional[datetime] = None
    result_json: Optional[dict[str, Any]] = None


class Approval(BaseRecord):
    """승인 이벤트"""

    approval_id: str = Field(default_factory=lambda: str(uuid4()))
    proposal_id: str
    chat_id: int
    decision: ApprovalDecision
    decided_at: datetime = Field(default_factory=datetime.now)
    actor: str = "HUMAN"
    note: Optional[str] = None


class ExternalRequest(BaseRecord):
    """외부 시스템 요청 (agent 연동)"""

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    proposal_id: Optional[str] = None
    target_system: str  # SANJAI_AGENT, OPENCLAW
    job_type: str
    payload_hash: str
    signature: str
    status: str = "PENDING"
    response_json: Optional[dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.now)
    sent_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class StrategyPack(BaseRecord):
    """전략 팩 (agent용 전략 메모)"""

    pack_id: str = Field(default_factory=lambda: str(uuid4()))
    case_id: str
    correlation_id: str
    issues: list[dict[str, Any]]
    advantage_points: list[dict[str, Any]]
    risk_points: list[dict[str, Any]]
    required_additional_evidence: list[dict[str, Any]]
    draft_instructions: list[dict[str, Any]]
    validation_status: ValidationStatus = ValidationStatus.PENDING
    validation_errors: Optional[list[str]] = None
    created_at: datetime = Field(default_factory=datetime.now)
    used_at: Optional[datetime] = None


class StrategyPackMetrics(BaseRecord):
    """전략 팩 품질 메트릭"""

    pack_id: str
    generated_claims: int = 0
    validated_claims: int = 0
    rejected_claims: int = 0
    new_facts_detected: int = 0  # 0이어야 함
    verifier_issues: int = 0
    revision_loops: int = 0
    total_cost_usd: float = 0.0
    final_rejected: bool = False


# ========== Helper Models for Operations ==========


class TerminationCondition(BaseModel):
    """종료 조건"""

    max_cost_usd: float = 5.0
    max_time_sec: int = 3600
    max_retries: int = 3
    max_rebuilds: int = 3


class HealthStatus(BaseModel):
    """헬스 체크 상태"""

    db_connected: bool
    db_wal_enabled: bool
    telegram_configured: bool
    vault_accessible: bool
    last_success_run: Optional[datetime]
    pending_jobs: int
    running_jobs: int
    active_runs: int
    insights_24h: int
    pending_proposals: int
    cost_24h_usd: float


class StatusResponse(BaseModel):
    """상태 응답"""

    correlation_id: str
    run_id: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    last_stage: Optional[str]
    event_count: int
    insights_count: int
    items_collected: int
    total_cost_usd: float
    errors: list[str]


class CostBreakdown(BaseModel):
    """비용 분석"""

    correlation_id: str
    total_cost_usd: float
    by_stage: dict[str, float]
    by_model: dict[str, float]
    total_tokens_in: int
    total_tokens_out: int
    call_count: int
    avg_latency_ms: float
