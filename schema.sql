-- sanjai-insight Database Schema v2.0
-- SQLite 3.x + WAL mode

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- Crawled Data (수집 원본)
CREATE TABLE IF NOT EXISTS crawled_data (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,  -- SUPREME_COURT, HIGH_COURT, KCOMWEL, MOEL, NAVER_TREND, COMPETITOR
    crawled_at TEXT NOT NULL,
    data_type TEXT NOT NULL,  -- PRECEDENT, POLICY, TREND, COMPETITOR_POST
    raw_content TEXT NOT NULL,
    metadata TEXT,  -- JSON
    status TEXT DEFAULT 'NEW',  -- NEW, INDEXED, ANALYZED, ARCHIVED
    crawled_by TEXT DEFAULT 'RAILWAY',  -- RAILWAY, OPENCLAW
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_crawled_data_source ON crawled_data(source);
CREATE INDEX idx_crawled_data_status ON crawled_data(status);
CREATE INDEX idx_crawled_data_crawled_at ON crawled_data(crawled_at);

-- Indexed Document (구조화 인덱스)
CREATE TABLE IF NOT EXISTS indexed_documents (
    id TEXT PRIMARY KEY,
    crawled_data_id TEXT,
    source_type TEXT NOT NULL,  -- VAULT, CRAWLED
    category TEXT NOT NULL,  -- PRECEDENT, LAW, CASE_DOC, BRIEF, RESEARCH, MARKETING, OPS
    subcategory TEXT,
    title TEXT NOT NULL,
    date TEXT,
    keywords TEXT,  -- JSON array
    entities TEXT,  -- JSON
    summary TEXT,
    embedding_id TEXT,
    indexed_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (crawled_data_id) REFERENCES crawled_data(id)
);

CREATE INDEX idx_indexed_documents_category ON indexed_documents(category);
CREATE INDEX idx_indexed_documents_date ON indexed_documents(date);

-- Insight (인사이트)
CREATE TABLE IF NOT EXISTS insights (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,  -- CASE_IMPACT, MARKET_OPPORTUNITY, STRATEGY_SHIFT
    trigger_data_ids TEXT NOT NULL,  -- JSON array
    title TEXT NOT NULL,
    body TEXT NOT NULL,  -- JSON (프레임별 구조화)
    confidence REAL NOT NULL,
    urgency TEXT NOT NULL,  -- HIGH, MEDIUM, LOW
    suggested_actions TEXT,  -- JSON array
    affected_cases TEXT,  -- JSON array
    created_at TEXT DEFAULT (datetime('now')),
    status TEXT DEFAULT 'NEW',  -- NEW, PROPOSED, ACCEPTED, REJECTED, EXPIRED
    model_used TEXT,
    tokens_used INTEGER DEFAULT 0
);

CREATE INDEX idx_insights_type ON insights(type);
CREATE INDEX idx_insights_status ON insights(status);
CREATE INDEX idx_insights_confidence ON insights(confidence);
CREATE INDEX idx_insights_created_at ON insights(created_at);

-- Proposal (제안)
CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    insight_id TEXT NOT NULL,
    message_text TEXT NOT NULL,
    proposed_at TEXT DEFAULT (datetime('now')),
    response TEXT DEFAULT 'PENDING',  -- PENDING, ACCEPTED, REJECTED, DEFERRED
    response_at TEXT,
    response_detail TEXT,
    executed_action TEXT,
    feedback TEXT,
    response_latency_sec INTEGER,
    FOREIGN KEY (insight_id) REFERENCES insights(id)
);

CREATE INDEX idx_proposals_insight_id ON proposals(insight_id);
CREATE INDEX idx_proposals_response ON proposals(response);
CREATE INDEX idx_proposals_proposed_at ON proposals(proposed_at);

-- Marketing Content (마케팅 콘텐츠)
CREATE TABLE IF NOT EXISTS marketing_content (
    id TEXT PRIMARY KEY,
    insight_id TEXT,
    content_type TEXT NOT NULL,  -- BLOG, SNS, NEWSLETTER
    title TEXT NOT NULL,
    target_keyword TEXT,
    seo_meta TEXT,  -- JSON
    draft TEXT NOT NULL,
    legal_review TEXT,  -- JSON
    status TEXT DEFAULT 'DRAFT',  -- DRAFT, REVIEWED, APPROVED, PUBLISHED
    published_url TEXT,
    performance TEXT,  -- JSON
    total_cost REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (insight_id) REFERENCES insights(id)
);

CREATE INDEX idx_marketing_content_status ON marketing_content(status);
CREATE INDEX idx_marketing_content_content_type ON marketing_content(content_type);

-- Trend Snapshot (트렌드 스냅샷)
CREATE TABLE IF NOT EXISTS trend_snapshots (
    id TEXT PRIMARY KEY,
    keyword TEXT NOT NULL,
    period TEXT NOT NULL,
    search_volume INTEGER,
    change_percent REAL,
    related_keywords TEXT,  -- JSON array
    captured_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_trend_snapshots_keyword ON trend_snapshots(keyword);
CREATE INDEX idx_trend_snapshots_captured_at ON trend_snapshots(captured_at);

-- Watch Log (크롤링 실행 로그)
CREATE TABLE IF NOT EXISTS watch_logs (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,  -- SUCCESS, FAILED, PARTIAL
    items_collected INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE INDEX idx_watch_logs_source ON watch_logs(source);
CREATE INDEX idx_watch_logs_started_at ON watch_logs(started_at);

-- System Metrics (v2 신규 — 자기진단용)
CREATE TABLE IF NOT EXISTS system_metrics (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL UNIQUE,
    total_insights INTEGER DEFAULT 0,
    high_confidence_ratio REAL DEFAULT 0,
    acceptance_rate REAL DEFAULT 0,
    avg_response_latency_sec REAL DEFAULT 0,
    total_cost_krw REAL DEFAULT 0,
    crawler_uptime_ratio REAL DEFAULT 0,
    top_rejection_reasons TEXT  -- JSON
);

CREATE INDEX idx_system_metrics_date ON system_metrics(date);

-- Prompt Versions (v2 신규 — 프롬프트 버전 관리)
CREATE TABLE IF NOT EXISTS prompt_versions (
    id TEXT PRIMARY KEY,
    engine TEXT NOT NULL,  -- think, propose, marketing
    version INTEGER NOT NULL,
    prompt_text TEXT NOT NULL,
    performance_score REAL,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_prompt_versions_engine ON prompt_versions(engine);
CREATE INDEX idx_prompt_versions_active ON prompt_versions(active);

-- Cost Log (v2 신규 — 비용 추적)
CREATE TABLE IF NOT EXISTS cost_log (
    id TEXT PRIMARY KEY,
    timestamp TEXT DEFAULT (datetime('now')),
    module TEXT NOT NULL,  -- think, marketing_ma, marketing_mb, etc.
    model TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_krw REAL,
    insight_id TEXT,
    FOREIGN KEY (insight_id) REFERENCES insights(id)
);

CREATE INDEX idx_cost_log_timestamp ON cost_log(timestamp);
CREATE INDEX idx_cost_log_module ON cost_log(module);
CREATE INDEX idx_cost_log_insight_id ON cost_log(insight_id);
