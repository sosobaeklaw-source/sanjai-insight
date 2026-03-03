# Compliance & Data Governance
## sanjai-insight System

> **Last Updated:** 2026-03-03
> **Owner:** Legal & Operations Team
> **Review Frequency:** Quarterly

---

## Table of Contents

1. [GDPR Compliance](#gdpr-compliance)
2. [Data Retention Policy](#data-retention-policy)
3. [Audit Log Requirements](#audit-log-requirements)
4. [Privacy by Design](#privacy-by-design)
5. [Data Subject Rights](#data-subject-rights)
6. [Security & Access Control](#security--access-control)

---

## GDPR Compliance

### Overview

The sanjai-insight system processes the following data categories:

| Data Type | Purpose | Legal Basis | Retention |
|-----------|---------|-------------|-----------|
| **Telegram User Data** | Bot interaction, approval tracking | Legitimate interest | 30 days |
| **LLM Call Logs** | Cost tracking, debugging | Legitimate interest | 90 days |
| **Crawled Content** | Legal research, insight generation | Legitimate interest | 30 days |
| **Vault Files** | Reference material indexing | Legitimate interest | Until deletion |
| **Audit Logs** | Security, compliance | Legal obligation | 365 days |

### GDPR Checklist

#### Article 5: Data Processing Principles

- [x] **Lawfulness, fairness, transparency**
  - Processing based on legitimate business interest
  - Privacy policy available to Telegram users
  - Clear purpose for each data type

- [x] **Purpose limitation**
  - Data used only for stated purposes
  - No secondary use without consent

- [x] **Data minimization**
  - Collect only necessary data
  - No PII stored beyond chat_id
  - Telegram usernames not persisted

- [x] **Accuracy**
  - Data sourced from authoritative sources
  - No user-generated PII

- [x] **Storage limitation**
  - Automated retention policies (30/90/365 days)
  - Regular cleanup jobs

- [x] **Integrity and confidentiality**
  - Encrypted at rest (Railway volume encryption)
  - Encrypted in transit (HTTPS, TLS)
  - Access controls (API keys, HMAC verification)

- [x] **Accountability**
  - Audit logs for all data access
  - DPO contact: legal@sosobaek.com

#### Article 25: Data Protection by Design

- [x] Pseudonymization: chat_id instead of username
- [x] Encryption: TLS, Railway volume encryption
- [x] Access control: HMAC signatures, rate limiting
- [x] Minimal data collection: No email, phone, name stored
- [x] Automated deletion: Retention policies enforced

#### Article 32: Security of Processing

- [x] **Technical Measures**
  - Encryption (TLS 1.2+, AES-256)
  - HMAC signature verification
  - Rate limiting (1000 req/hour per IP)
  - Regular security updates

- [x] **Organizational Measures**
  - Access controls (API keys rotated quarterly)
  - Backup procedures (daily backups, 30-day retention)
  - Incident response plan (see DISASTER_RECOVERY.md)

---

## Data Retention Policy

### Retention Periods

| Data Category | Retention Period | Deletion Method | Automation |
|---------------|------------------|-----------------|------------|
| **Telegram Updates** | 30 days | Hard delete | Daily cleanup job |
| **Jobs** | 30 days | Hard delete | Daily cleanup job |
| **Runlogs** | 90 days | Soft delete (archive) | Weekly cleanup job |
| **LLM Calls** | 90 days | Hard delete | Weekly cleanup job |
| **Events** | 90 days | Hard delete | Weekly cleanup job |
| **Insights** | 90 days | Soft delete (flag) | Weekly cleanup job |
| **Proposals** | 90 days | Soft delete (flag) | Weekly cleanup job |
| **Approvals** | 365 days | Hard delete | Quarterly cleanup job |
| **Source Items** | 30 days | Hard delete | Daily cleanup job |
| **Vault Files** | Until manual deletion | Hard delete | N/A |
| **Audit Logs** | 365 days | Archive to S3 | Monthly archive job |

### Cleanup Jobs

**Daily Cleanup (03:00 UTC):**
```sql
-- Telegram updates older than 30 days
DELETE FROM telegram_updates WHERE processed_at < datetime('now', '-30 days');

-- Source items older than 30 days
DELETE FROM source_items WHERE fetched_at < datetime('now', '-30 days');

-- Jobs older than 30 days (completed or failed)
DELETE FROM jobs WHERE status IN ('COMPLETED', 'FAILED') AND completed_at < datetime('now', '-30 days');
```

**Weekly Cleanup (Sunday 03:00 UTC):**
```sql
-- Runlogs older than 90 days
DELETE FROM runlogs WHERE ended_at < datetime('now', '-90 days');

-- LLM calls older than 90 days
DELETE FROM llm_calls WHERE created_at < datetime('now', '-90 days');

-- Events older than 90 days
DELETE FROM events WHERE created_at < datetime('now', '-90 days');
```

**Quarterly Cleanup (1st of quarter, 03:00 UTC):**
```sql
-- Approvals older than 365 days
DELETE FROM approvals WHERE decided_at < datetime('now', '-365 days');

-- Audit logs older than 365 days (archive first)
INSERT INTO audit_log_archive SELECT * FROM audit_log WHERE created_at < datetime('now', '-365 days');
DELETE FROM audit_log WHERE created_at < datetime('now', '-365 days');
```

### Manual Deletion Requests

Users can request deletion of their data by contacting: legal@sosobaek.com

**Response Time:** Within 30 days (GDPR Article 12)

**Deletion Scope:**
- All records with matching chat_id
- Associated proposals, approvals
- Audit logs (anonymized, not deleted per legal obligation)

---

## Audit Log Requirements

### Audit Log Table

```sql
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
```

### Auditable Events

**Data Access:**
- Telegram user requests (/status, /cost)
- API queries (/api/cost, /api/metrics)
- Database queries on sensitive tables

**Data Modification:**
- Proposal approvals
- Job creation/deletion
- Configuration changes

**Security Events:**
- Authentication failures
- Rate limit violations
- Invalid HMAC signatures

**Compliance Events:**
- Data deletion requests
- Retention policy execution
- Audit log exports

### Audit Log Retention

- **Primary:** 365 days in database
- **Archive:** 7 years in S3 (encrypted)
- **Access:** Admin-only, logged

---

## Privacy by Design

### Principles Implemented

#### 1. Proactive not Reactive

- Rate limiting prevents abuse
- Input validation prevents injection
- HMAC signatures prevent spoofing

#### 2. Privacy as Default

- Minimal data collection (chat_id only)
- No tracking beyond operational needs
- Automatic deletion after retention period

#### 3. Privacy Embedded into Design

- No PII in logs (redacted)
- Pseudonymization (hashed identifiers)
- Separation of concerns (data vs. audit)

#### 4. Full Functionality

- Privacy measures don't hinder functionality
- Performance optimizations (caching, indexes)

#### 5. End-to-End Security

- Encryption in transit (TLS)
- Encryption at rest (Railway volume)
- Secure key management (Railway secrets)

#### 6. Visibility and Transparency

- Users can query their data (/mystatus)
- Audit logs for all operations
- Privacy policy available

#### 7. Respect for User Privacy

- Users can opt-out (stop using bot)
- Data deletion on request
- Minimal retention periods

---

## Data Subject Rights

### Right to Access (Article 15)

**Request Method:** Contact legal@sosobaek.com
**Response Time:** 30 days
**Format:** JSON export

**Data Provided:**
- All proposals linked to chat_id
- All approvals made
- Telegram interaction history

**Implementation:**
```python
# src/utils/gdpr_tools.py: export_user_data(chat_id)
```

### Right to Rectification (Article 16)

**Not Applicable:** System does not store user-submitted PII.

### Right to Erasure (Article 17)

**Request Method:** Contact legal@sosobaek.com
**Response Time:** 30 days

**Scope:**
- Delete all proposals with chat_id
- Delete all approvals with chat_id
- Anonymize audit logs (replace chat_id with "DELETED_USER")

**Implementation:**
```python
# src/utils/gdpr_tools.py: delete_user_data(chat_id)
```

### Right to Restrict Processing (Article 18)

**Request Method:** Contact legal@sosobaek.com

**Implementation:**
- Add chat_id to exclusion list
- Block future bot interactions
- Flag existing data as "restricted"

### Right to Data Portability (Article 20)

**Request Method:** Contact legal@sosobaek.com
**Format:** JSON export
**Scope:** All user-related data

### Right to Object (Article 21)

**Implementation:**
- User can stop using bot (automatic opt-out)
- Data deleted per retention policy

---

## Security & Access Control

### Access Control Matrix

| Resource | Admin | System | User | Public |
|----------|-------|--------|------|--------|
| **Database** | Full | Read/Write | No | No |
| **API (Cost)** | Yes | Yes | Yes | No |
| **API (Metrics)** | Yes | Yes | No | No |
| **API (Health)** | Yes | Yes | Yes | Yes |
| **Backups** | Yes | Yes | No | No |
| **Audit Logs** | Yes | No | No | No |
| **Telegram Bot** | No | Yes | Yes | No |

### Authentication Methods

- **API:** HMAC signatures (internal services)
- **Telegram:** Bot token + webhook secret
- **Admin:** Railway CLI + MFA

### Encryption

- **In Transit:** TLS 1.2+ (all connections)
- **At Rest:** Railway volume encryption (AES-256)
- **Backups:** GPG encryption + S3 SSE

### Key Rotation

- **Telegram Bot Token:** Annually
- **HMAC Secrets:** Quarterly
- **API Keys:** Quarterly
- **Backup Encryption Keys:** Annually

---

## Incident Response

### Data Breach Protocol

**1. Detection (0-1 hour):**
- Alert triggered (Sentry, monitoring)
- Initial assessment

**2. Containment (1-4 hours):**
- Isolate affected systems
- Revoke compromised credentials
- Enable rate limiting

**3. Investigation (4-24 hours):**
- Review audit logs
- Identify breach scope
- Assess data impact

**4. Notification (24-72 hours):**
- Notify DPA if required (72 hours per GDPR)
- Notify affected users
- Public disclosure if needed

**5. Recovery (1-7 days):**
- Restore from backups if needed
- Apply security patches
- Resume normal operations

**6. Post-Mortem (7-14 days):**
- Root cause analysis
- Update procedures
- Implement preventive measures

### Contact Information

- **DPO:** legal@sosobaek.com
- **Security Team:** security@sosobaek.com
- **On-Call:** +82-XX-XXXX-XXXX

---

## Compliance Checklist

### Monthly

- [ ] Review audit logs for anomalies
- [ ] Check backup integrity
- [ ] Verify retention policy execution

### Quarterly

- [ ] Rotate API keys and secrets
- [ ] Review access control list
- [ ] Update privacy policy if needed
- [ ] DPO review of procedures

### Annually

- [ ] Full GDPR compliance audit
- [ ] Security penetration testing
- [ ] Update this document
- [ ] Staff training on data protection

---

## References

- **GDPR Full Text:** https://gdpr-info.eu/
- **ICO Guidance:** https://ico.org.uk/for-organisations/
- **EDPB Guidelines:** https://edpb.europa.eu/

---

**Document Version:** 1.0
**Approved By:** Legal Team
**Next Review:** 2026-06-01
