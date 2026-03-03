-- Performance Indexes for sanjai-insight
-- Add to existing schema_v2_operational.sql for query optimization
-- SQLite 3.x optimized indexes

PRAGMA foreign_keys = ON;

-- ========== Cost Analysis Indexes ==========

-- Optimize cost queries by date range
CREATE INDEX IF NOT EXISTS idx_llm_calls_cost_date
ON llm_calls(created_at, cost_usd);

-- Optimize cost by stage queries
CREATE INDEX IF NOT EXISTS idx_llm_calls_stage_cost
ON llm_calls(stage, cost_usd, created_at);

-- Optimize model cost breakdown
CREATE INDEX IF NOT EXISTS idx_llm_calls_model_cost
ON llm_calls(model, cost_usd, created_at);

-- Composite index for aggregations
CREATE INDEX IF NOT EXISTS idx_llm_calls_composite
ON llm_calls(correlation_id, stage, model, created_at);

-- ========== Status & Health Check Indexes ==========

-- Optimize job queue queries
CREATE INDEX IF NOT EXISTS idx_jobs_status_created
ON jobs(status, created_at);

-- Optimize runlog status queries
CREATE INDEX IF NOT EXISTS idx_runlogs_status_started
ON runlogs(status, started_at);

-- Optimize checkpoint lookups
CREATE INDEX IF NOT EXISTS idx_checkpoints_updated
ON checkpoints(updated_at);

-- ========== Approval & Proposal Indexes ==========

-- Optimize approval rate queries
CREATE INDEX IF NOT EXISTS idx_approvals_decision_date
ON approvals(decision, decided_at);

-- Optimize pending proposals
CREATE INDEX IF NOT EXISTS idx_proposals_response_created
ON proposals(response, created_at);

-- ========== Quality Metrics Indexes ==========

-- Optimize validation status queries
CREATE INDEX IF NOT EXISTS idx_strategy_packs_validation
ON strategy_packs(validation_status, created_at);

-- Optimize strategy pack metrics
CREATE INDEX IF NOT EXISTS idx_strategy_pack_metrics_pack
ON strategy_pack_metrics(pack_id, created_at);

-- ========== Alert & Monitoring Indexes ==========

-- Optimize active alerts queries
CREATE INDEX IF NOT EXISTS idx_alerts_resolved_triggered
ON alerts(resolved, triggered_at);

-- Optimize alert rule lookups
CREATE INDEX IF NOT EXISTS idx_alerts_rule_resolved
ON alerts(rule_name, resolved, triggered_at);

-- ========== Vault & Evidence Indexes ==========

-- Optimize vault file lookups by category
CREATE INDEX IF NOT EXISTS idx_vault_files_category_indexed
ON vault_files(category, indexed_at);

-- Optimize evidence correlation lookups
CREATE INDEX IF NOT EXISTS idx_evidence_correlation_source
ON evidence(correlation_id, source_type);

-- ========== Source Item Indexes ==========

-- Optimize source item fetching
CREATE INDEX IF NOT EXISTS idx_source_items_source_fetched
ON source_items(source_id, fetched_at);

-- ========== Event Log Indexes ==========

-- Optimize event queries by type and correlation
CREATE INDEX IF NOT EXISTS idx_events_type_correlation
ON events(type, correlation_id, ts);

-- ========== Covering Indexes (Read-Heavy Queries) ==========

-- Covering index for cost dashboard (reduces table lookups)
CREATE INDEX IF NOT EXISTS idx_llm_calls_dashboard_cover
ON llm_calls(created_at, stage, model, cost_usd, tokens_in, tokens_out);

-- Covering index for health check view
CREATE INDEX IF NOT EXISTS idx_runlogs_health_cover
ON runlogs(status, started_at, ended_at, total_cost_usd, correlation_id);

-- ========== Analyze Tables for Query Planner ==========

-- Update SQLite statistics for better query planning
ANALYZE;

-- ========== Verify Indexes ==========

-- Query to check all indexes on a table:
-- SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='llm_calls';

-- Query to see index usage:
-- EXPLAIN QUERY PLAN SELECT ... FROM llm_calls WHERE ...;
