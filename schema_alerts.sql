-- Alert System Tables
-- Extends schema_v2_operational.sql

PRAGMA foreign_keys = ON;

-- Alerts (알림 히스토리)
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    rule_name TEXT NOT NULL,
    severity TEXT NOT NULL,  -- INFO, WARNING, ERROR, CRITICAL
    message TEXT NOT NULL,
    correlation_id TEXT,
    metadata_json TEXT,
    triggered_at TEXT DEFAULT (datetime('now')),
    resolved INTEGER DEFAULT 0,
    resolved_at TEXT,
    notified INTEGER DEFAULT 0,
    notification_attempts INTEGER DEFAULT 0
);

CREATE INDEX idx_alerts_rule_name ON alerts(rule_name);
CREATE INDEX idx_alerts_severity ON alerts(severity);
CREATE INDEX idx_alerts_triggered_at ON alerts(triggered_at);
CREATE INDEX idx_alerts_resolved ON alerts(resolved);
CREATE INDEX idx_alerts_correlation_id ON alerts(correlation_id);
