-- sanjai-insight Operational Schema v2.0
-- Extension to base schema.sql with operational tables
-- SQLite 3.x + WAL mode + FTS5

PRAGMA foreign_keys = ON;

-- ========== WP-1: Core Operational Tables ==========

-- Telegram Updates (멱등성)
CREATE TABLE IF NOT EXISTS telegram_updates (
    update_id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    processed_at TEXT DEFAULT (datetime('now')),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_telegram_updates_chat_id ON telegram_updates(chat_id);
CREATE INDEX idx_telegram_updates_processed_at ON telegram_updates(processed_at);

-- Jobs (스케줄러)
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    job_key TEXT UNIQUE NOT NULL,  -- 멱등성 키 (예: "WATCH_DAILY:2026-03-03")
    type TEXT NOT NULL,  -- WATCH, THINK, PROPOSE, MARKETING
    payload_json TEXT NOT NULL,
    status TEXT DEFAULT 'PENDING',  -- PENDING, RUNNING, COMPLETED, FAILED
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    created_at TEXT DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT,
    last_error TEXT
);

CREATE INDEX idx_jobs_job_key ON jobs(job_key);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);

-- Run Logs (실행 추적)
CREATE TABLE IF NOT EXISTS runlogs (
    run_id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,  -- 실행 단위 (예: "DAILY_WATCH:2026-03-03")
    job_id TEXT,
    status TEXT NOT NULL,  -- RUNNING, COMPLETED, FAILED, TERMINATED
    started_at TEXT NOT NULL,
    ended_at TEXT,
    total_cost_usd REAL DEFAULT 0.0,
    total_tokens INTEGER DEFAULT 0,
    meta_json TEXT,  -- JSON: stages, errors, metrics
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);

CREATE INDEX idx_runlogs_correlation_id ON runlogs(correlation_id);
CREATE INDEX idx_runlogs_status ON runlogs(status);
CREATE INDEX idx_runlogs_started_at ON runlogs(started_at);

-- Checkpoints (재개)
CREATE TABLE IF NOT EXISTS checkpoints (
    correlation_id TEXT PRIMARY KEY,
    last_stage TEXT NOT NULL,
    ctx_json TEXT NOT NULL,  -- JSON: 전체 컨텍스트
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_checkpoints_updated_at ON checkpoints(updated_at);

-- Events (append-only 감사로그)
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    type TEXT NOT NULL,  -- WATCH_START, WATCH_END, INSIGHT_CREATED, PROPOSAL_SENT, etc.
    correlation_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_events_correlation_id ON events(correlation_id);
CREATE INDEX idx_events_type ON events(type);
CREATE INDEX idx_events_ts ON events(ts);

-- LLM Calls (비용 추적 - 더 상세)
CREATE TABLE IF NOT EXISTS llm_calls (
    id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    run_id TEXT,
    stage TEXT NOT NULL,  -- WATCH, THINK, PROPOSE, MARKETING_MA, etc.
    model TEXT NOT NULL,
    tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    latency_ms INTEGER,
    cost_usd REAL NOT NULL,
    meta_json TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (run_id) REFERENCES runlogs(run_id)
);

CREATE INDEX idx_llm_calls_correlation_id ON llm_calls(correlation_id);
CREATE INDEX idx_llm_calls_run_id ON llm_calls(run_id);
CREATE INDEX idx_llm_calls_stage ON llm_calls(stage);
CREATE INDEX idx_llm_calls_created_at ON llm_calls(created_at);

-- ========== WP-3: Vault Indexing (증분 + FTS5) ==========

-- Vault Files (증분 인덱싱)
CREATE TABLE IF NOT EXISTS vault_files (
    file_id TEXT PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    sha256 TEXT NOT NULL,
    mtime TEXT NOT NULL,
    size INTEGER NOT NULL,
    title TEXT,
    category TEXT,  -- PRECEDENT, LAW, CASE_DOC, BRIEF, RESEARCH, MARKETING, OPS
    metadata_json TEXT,
    indexed_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_vault_files_path ON vault_files(path);
CREATE INDEX idx_vault_files_sha256 ON vault_files(sha256);
CREATE INDEX idx_vault_files_category ON vault_files(category);
CREATE INDEX idx_vault_files_indexed_at ON vault_files(indexed_at);

-- Vault Chunks (청크 단위)
CREATE TABLE IF NOT EXISTS vault_chunks (
    chunk_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    text TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (file_id) REFERENCES vault_files(file_id) ON DELETE CASCADE
);

CREATE INDEX idx_vault_chunks_file_id ON vault_chunks(file_id);
CREATE INDEX idx_vault_chunks_sha256 ON vault_chunks(sha256);

-- FTS5 Virtual Table (전체 텍스트 검색)
CREATE VIRTUAL TABLE IF NOT EXISTS vault_fts USING fts5(
    chunk_id UNINDEXED,
    text,
    title,
    category,
    path,
    content='vault_chunks',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

-- FTS5 triggers for auto-sync
CREATE TRIGGER IF NOT EXISTS vault_chunks_ai AFTER INSERT ON vault_chunks BEGIN
    INSERT INTO vault_fts(rowid, chunk_id, text, title, category, path)
    SELECT
        NEW.rowid,
        NEW.chunk_id,
        NEW.text,
        vf.title,
        vf.category,
        vf.path
    FROM vault_files vf
    WHERE vf.file_id = NEW.file_id;
END;

CREATE TRIGGER IF NOT EXISTS vault_chunks_ad AFTER DELETE ON vault_chunks BEGIN
    DELETE FROM vault_fts WHERE rowid = OLD.rowid;
END;

CREATE TRIGGER IF NOT EXISTS vault_chunks_au AFTER UPDATE ON vault_chunks BEGIN
    UPDATE vault_fts
    SET text = NEW.text
    WHERE rowid = NEW.rowid;
END;

-- ========== WP-4: Watch (외부 수집) ==========

-- Sources (수집 소스 설정)
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,  -- SUPREME_COURT, HIGH_COURT, KCOMWEL, MOEL, NAVER_TREND, COMPETITOR
    base_url TEXT,
    config_json TEXT,  -- JSON: credentials, limits, etc.
    enabled INTEGER DEFAULT 1,
    last_success_at TEXT,
    last_error TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_sources_type ON sources(type);
CREATE INDEX idx_sources_enabled ON sources(enabled);

-- Source Items (수집 아이템 - 증분)
CREATE TABLE IF NOT EXISTS source_items (
    item_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    external_key TEXT UNIQUE NOT NULL,  -- 외부 시스템 ID (멱등 키)
    fetched_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (source_id) REFERENCES sources(source_id)
);

CREATE INDEX idx_source_items_source_id ON source_items(source_id);
CREATE INDEX idx_source_items_external_key ON source_items(external_key);
CREATE INDEX idx_source_items_fetched_at ON source_items(fetched_at);
CREATE INDEX idx_source_items_content_hash ON source_items(content_hash);

-- ========== WP-5: Think (근거 기반 인사이트) ==========

-- Evidence (근거)
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    source_type TEXT NOT NULL,  -- VAULT, CRAWLED, SOURCE_ITEM
    locator_json TEXT NOT NULL,  -- JSON: {file_path, chunk_id, line_range} or {url, item_id}
    snippet TEXT NOT NULL,  -- 실제 근거 텍스트 (최대 500자)
    content_hash TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_evidence_correlation_id ON evidence(correlation_id);
CREATE INDEX idx_evidence_source_type ON evidence(source_type);
CREATE INDEX idx_evidence_content_hash ON evidence(content_hash);

-- Insight Claims (claim-evidence 바인딩)
CREATE TABLE IF NOT EXISTS insight_claims (
    claim_id TEXT PRIMARY KEY,
    insight_id TEXT NOT NULL,
    text TEXT NOT NULL,  -- claim 문장
    evidence_ids_json TEXT NOT NULL,  -- JSON array: ["E1", "E2"] (최소 1개 필수)
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (insight_id) REFERENCES insights(id) ON DELETE CASCADE
);

CREATE INDEX idx_insight_claims_insight_id ON insight_claims(insight_id);

-- Insights (인사이트)
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

CREATE INDEX IF NOT EXISTS idx_insights_type ON insights(type);
CREATE INDEX IF NOT EXISTS idx_insights_status ON insights(status);
CREATE INDEX IF NOT EXISTS idx_insights_created_at ON insights(created_at);

-- ========== WP-6: Propose (승인 기반 실행) ==========

-- Proposals (제안)
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

CREATE INDEX IF NOT EXISTS idx_proposals_insight_id ON proposals(insight_id);
CREATE INDEX IF NOT EXISTS idx_proposals_response ON proposals(response);

-- Proposal Actions (제안 액션)
CREATE TABLE IF NOT EXISTS proposal_actions (
    id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    action_type TEXT NOT NULL,  -- ADD_PRECEDENT, RUN_DRAFTER, GENERATE_LEAD, PUBLISH_BLOG, etc.
    action_payload_json TEXT NOT NULL,
    requires_approval INTEGER DEFAULT 1,  -- 0: 자동실행, 1: 승인필요
    executed INTEGER DEFAULT 0,
    executed_at TEXT,
    result_json TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (proposal_id) REFERENCES proposals(id) ON DELETE CASCADE
);

CREATE INDEX idx_proposal_actions_proposal_id ON proposal_actions(proposal_id);
CREATE INDEX idx_proposal_actions_executed ON proposal_actions(executed);

-- Approvals (승인 이벤트)
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    decision TEXT NOT NULL,  -- APPROVE, REJECT, DEFER, DRAFT_ONLY
    decided_at TEXT DEFAULT (datetime('now')),
    actor TEXT,  -- "HUMAN" or "SYSTEM"
    note TEXT,
    UNIQUE(proposal_id, chat_id),  -- 중복 클릭 방어
    FOREIGN KEY (proposal_id) REFERENCES proposals(id)
);

CREATE INDEX idx_approvals_proposal_id ON approvals(proposal_id);
CREATE INDEX idx_approvals_decision ON approvals(decision);
CREATE INDEX idx_approvals_decided_at ON approvals(decided_at);

-- ========== WP-7: Agent Integration ==========

-- External Requests (agent 연동 요청)
CREATE TABLE IF NOT EXISTS external_requests (
    request_id TEXT PRIMARY KEY,
    proposal_id TEXT,
    target_system TEXT NOT NULL,  -- "SANJAI_AGENT", "OPENCLAW", etc.
    job_type TEXT NOT NULL,  -- ADD_PRECEDENT_TO_CASE, RUN_LEGAL_DRAFTER, etc.
    payload_hash TEXT NOT NULL,
    signature TEXT NOT NULL,  -- HMAC-SHA256
    status TEXT DEFAULT 'PENDING',  -- PENDING, SENT, ACK, COMPLETED, FAILED
    response_json TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    sent_at TEXT,
    completed_at TEXT,
    FOREIGN KEY (proposal_id) REFERENCES proposals(id)
);

CREATE INDEX idx_external_requests_proposal_id ON external_requests(proposal_id);
CREATE INDEX idx_external_requests_target_system ON external_requests(target_system);
CREATE INDEX idx_external_requests_status ON external_requests(status);

-- ========== Strategy Bot (Addendum) ==========

-- Strategy Packs (전략 메모 - agent용)
CREATE TABLE IF NOT EXISTS strategy_packs (
    pack_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,  -- sanjai-agent case ID
    correlation_id TEXT NOT NULL,
    issues TEXT NOT NULL,  -- JSON array
    advantage_points TEXT NOT NULL,  -- JSON array
    risk_points TEXT NOT NULL,  -- JSON array
    required_additional_evidence TEXT,  -- JSON array
    draft_instructions TEXT NOT NULL,  -- JSON array
    validation_status TEXT DEFAULT 'PENDING',  -- PENDING, PASS, FAIL
    validation_errors TEXT,  -- JSON array
    created_at TEXT DEFAULT (datetime('now')),
    used_at TEXT
);

CREATE INDEX idx_strategy_packs_case_id ON strategy_packs(case_id);
CREATE INDEX idx_strategy_packs_correlation_id ON strategy_packs(correlation_id);
CREATE INDEX idx_strategy_packs_validation_status ON strategy_packs(validation_status);

-- Strategy Pack Metrics (품질 추적)
CREATE TABLE IF NOT EXISTS strategy_pack_metrics (
    id TEXT PRIMARY KEY,
    pack_id TEXT NOT NULL,
    generated_claims INTEGER DEFAULT 0,
    validated_claims INTEGER DEFAULT 0,
    rejected_claims INTEGER DEFAULT 0,
    new_facts_detected INTEGER DEFAULT 0,  -- 0이어야 함
    verifier_issues INTEGER DEFAULT 0,
    revision_loops INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0.0,
    final_rejected INTEGER DEFAULT 0,  -- 1이면 팩 폐기
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (pack_id) REFERENCES strategy_packs(pack_id)
);

CREATE INDEX idx_strategy_pack_metrics_pack_id ON strategy_pack_metrics(pack_id);

-- ========== Views for Operations ==========

-- Health Check View
CREATE VIEW IF NOT EXISTS v_health_summary AS
SELECT
    (SELECT COUNT(*) FROM jobs WHERE status = 'PENDING') as pending_jobs,
    (SELECT COUNT(*) FROM jobs WHERE status = 'RUNNING') as running_jobs,
    (SELECT COUNT(*) FROM runlogs WHERE status = 'RUNNING') as active_runs,
    (SELECT MAX(started_at) FROM runlogs WHERE status = 'COMPLETED') as last_success_run,
    (SELECT COUNT(*) FROM insights WHERE created_at >= datetime('now', '-24 hours')) as insights_24h,
    (SELECT COUNT(*) FROM proposals WHERE response = 'PENDING') as pending_proposals,
    (SELECT SUM(cost_usd) FROM llm_calls WHERE created_at >= datetime('now', '-24 hours')) as cost_24h_usd;

-- Status View (correlation_id별)
CREATE VIEW IF NOT EXISTS v_run_status AS
SELECT
    rl.correlation_id,
    rl.run_id,
    rl.status,
    rl.started_at,
    rl.ended_at,
    rl.total_cost_usd,
    cp.last_stage,
    (SELECT COUNT(*) FROM events WHERE correlation_id = rl.correlation_id) as event_count,
    (SELECT COUNT(*) FROM insights WHERE id IN (
        SELECT JSON_EXTRACT(payload_json, '$.insight_id')
        FROM events
        WHERE correlation_id = rl.correlation_id AND type = 'INSIGHT_CREATED'
    )) as insights_count,
    (SELECT COUNT(*) FROM source_items WHERE item_id IN (
        SELECT JSON_EXTRACT(payload_json, '$.item_id')
        FROM events
        WHERE correlation_id = rl.correlation_id AND type = 'ITEM_COLLECTED'
    )) as items_collected
FROM runlogs rl
LEFT JOIN checkpoints cp ON rl.correlation_id = cp.correlation_id;

-- Cost View (correlation_id별)
CREATE VIEW IF NOT EXISTS v_cost_breakdown AS
SELECT
    correlation_id,
    stage,
    model,
    COUNT(*) as call_count,
    SUM(tokens_in) as total_tokens_in,
    SUM(tokens_out) as total_tokens_out,
    SUM(cost_usd) as total_cost_usd,
    AVG(latency_ms) as avg_latency_ms,
    MIN(created_at) as first_call,
    MAX(created_at) as last_call
FROM llm_calls
GROUP BY correlation_id, stage, model;
