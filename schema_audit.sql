-- Audit Log Schema Extension
-- Compliance and data governance

PRAGMA foreign_keys = ON;

-- Audit Log
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,  -- DATA_ACCESS, DATA_DELETION, CONFIG_CHANGE, etc.
    actor TEXT NOT NULL,  -- USER, SYSTEM, ADMIN
    actor_id TEXT,  -- chat_id, IP, user_id
    resource_type TEXT NOT NULL,  -- TABLE, FILE, API
    resource_id TEXT NOT NULL,
    action TEXT NOT NULL,  -- READ, WRITE, DELETE, UPDATE
    metadata_json TEXT,  -- Context data
    ip_address TEXT,
    user_agent TEXT,
    result TEXT NOT NULL,  -- SUCCESS, FAILURE, DENIED
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX idx_audit_log_event_type ON audit_log(event_type);
CREATE INDEX idx_audit_log_actor ON audit_log(actor, actor_id);
CREATE INDEX idx_audit_log_resource ON audit_log(resource_type, resource_id);
CREATE INDEX idx_audit_log_result ON audit_log(result);
CREATE INDEX idx_audit_log_created ON audit_log(created_at);
