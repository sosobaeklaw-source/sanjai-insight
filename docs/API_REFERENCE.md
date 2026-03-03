# API Reference
## sanjai-insight REST API

> **Version:** 2.0
> **Base URL:** `https://your-app.railway.app`
> **Authentication:** HMAC signatures for internal endpoints

---

## Table of Contents

1. [Health & Status](#health--status)
2. [Cost Management](#cost-management)
3. [Metrics](#metrics)
4. [Telegram Webhook](#telegram-webhook)
5. [Internal APIs](#internal-apis)
6. [Error Codes](#error-codes)

---

## Health & Status

### GET /health

Comprehensive health check with system metrics.

**Authentication:** None (public)

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-03-03T12:00:00Z",
  "version": "2.0",
  "uptime_seconds": 86400,
  "database": {
    "status": "connected",
    "size_mb": 128.5,
    "integrity": "ok"
  },
  "workers": {
    "active": 4,
    "total": 8,
    "queue_size": 2
  },
  "jobs": {
    "pending": 3,
    "running": 1
  },
  "last_run": "2026-03-03T11:00:00Z"
}
```

**Status Codes:**
- `200 OK` - System healthy
- `503 Service Unavailable` - System unhealthy

---

### GET /healthz

Simple health check for load balancers.

**Authentication:** None (public)

**Response:**
```json
{"status": "ok"}
```

**Status Codes:**
- `200 OK` - Service is up

---

### GET /api/status

Detailed system status with recent activity.

**Authentication:** None (public)

**Query Parameters:**
- `correlation_id` (optional): Filter by correlation ID

**Response:**
```json
{
  "pending_jobs": 3,
  "running_jobs": 1,
  "active_runs": 1,
  "last_success_run": "2026-03-03T11:00:00Z",
  "insights_24h": 12,
  "pending_proposals": 2,
  "cost_24h_usd": 3.45,
  "recent_runs": [
    {
      "correlation_id": "DAILY_WATCH:2026-03-03",
      "status": "RUNNING",
      "started_at": "2026-03-03T10:00:00Z",
      "current_stage": "THINK"
    }
  ]
}
```

---

## Cost Management

### GET /api/cost

Get cost breakdown by time period.

**Authentication:** Optional (API key for detailed view)

**Query Parameters:**
- `days` (default: 7): Number of days to analyze
- `correlation_id` (optional): Filter by correlation ID
- `stage` (optional): Filter by stage (WATCH, THINK, PROPOSE, etc.)
- `model` (optional): Filter by LLM model

**Response:**
```json
{
  "period_days": 7,
  "start_date": "2026-02-25T00:00:00Z",
  "end_date": "2026-03-03T00:00:00Z",
  "total_cost_usd": 24.56,
  "total_calls": 342,
  "avg_cost_per_call": 0.072,
  "total_tokens": 1245678,
  "by_stage": [
    {
      "stage": "THINK",
      "cost_usd": 12.34,
      "calls": 123,
      "percentage": 50.2
    },
    {
      "stage": "PROPOSE",
      "cost_usd": 8.22,
      "calls": 89,
      "percentage": 33.5
    }
  ],
  "by_model": [
    {
      "model": "gpt-4",
      "cost_usd": 18.90,
      "calls": 198,
      "percentage": 77.0
    },
    {
      "model": "gpt-3.5-turbo",
      "cost_usd": 5.66,
      "calls": 144,
      "percentage": 23.0
    }
  ],
  "daily_breakdown": [
    {
      "date": "2026-03-03",
      "cost_usd": 3.45,
      "calls": 48
    }
  ]
}
```

---

### GET /api/cost/forecast

Forecast cost for next 30 days based on trends.

**Authentication:** Required

**Response:**
```json
{
  "current_daily_avg": 3.51,
  "forecast_30d": 105.30,
  "trend": "stable",
  "confidence": 0.85,
  "recommendations": [
    "Cost within expected range",
    "Consider caching for THINK stage"
  ]
}
```

---

## Metrics

### GET /api/metrics

Get quality and performance metrics.

**Authentication:** Optional

**Query Parameters:**
- `period` (default: 7d): Time period (1d, 7d, 30d, 90d)
- `metric_type` (optional): Filter by type (quality, performance, approval)

**Response:**
```json
{
  "period": "7d",
  "timestamp": "2026-03-03T12:00:00Z",
  "quality": {
    "validation_pass_rate": 0.85,
    "total_packs": 67,
    "passed": 57,
    "failed": 10,
    "avg_claims_per_pack": 4.2,
    "avg_evidence_per_claim": 2.1
  },
  "approval": {
    "approval_rate": 0.72,
    "total_proposals": 45,
    "approved": 32,
    "rejected": 8,
    "deferred": 5
  },
  "performance": {
    "avg_latency_ms": 1842,
    "p95_latency_ms": 3120,
    "p99_latency_ms": 4560,
    "failure_rate": 0.03
  },
  "productivity": {
    "insights_generated": 67,
    "proposals_sent": 45,
    "actions_executed": 32,
    "avg_time_to_approval_hours": 4.2
  }
}
```

---

### GET /api/metrics/quality

Detailed quality metrics.

**Authentication:** Required

**Response:**
```json
{
  "validation": {
    "pass_rate_7d": 0.85,
    "pass_rate_30d": 0.82,
    "trend": "improving",
    "common_failures": [
      {
        "error": "Insufficient evidence",
        "count": 5,
        "percentage": 50.0
      }
    ]
  },
  "evidence": {
    "avg_per_claim": 2.1,
    "source_distribution": {
      "VAULT": 0.65,
      "CRAWLED": 0.30,
      "SOURCE_ITEM": 0.05
    }
  },
  "insights": {
    "total_generated": 67,
    "actionable": 45,
    "actionable_rate": 0.67
  }
}
```

---

## Telegram Webhook

### POST /telegram/webhook

Telegram bot webhook endpoint.

**Authentication:** HMAC signature (X-Telegram-Bot-Api-Secret-Token)

**Request Body:**
```json
{
  "update_id": 123456789,
  "message": {
    "message_id": 789,
    "from": {
      "id": 12345,
      "first_name": "User"
    },
    "chat": {
      "id": 12345,
      "type": "private"
    },
    "date": 1709467200,
    "text": "/status"
  }
}
```

**Response:**
```json
{
  "ok": true,
  "processed": true
}
```

**Supported Commands:**
- `/start` - Initialize bot
- `/status` - System status
- `/cost [days]` - Cost report
- `/metrics` - Quality metrics
- `/jobs` - Job queue status
- `/help` - Command list

---

## Internal APIs

### POST /internal/jobs

Create job (internal service-to-service).

**Authentication:** HMAC signature (X-Internal-Signature)

**Request Body:**
```json
{
  "type": "ADD_PRECEDENT_TO_CASE",
  "payload": {
    "case_id": "CASE-2026-001",
    "precedent_id": "PREC-001",
    "correlation_id": "DAILY_WATCH:2026-03-03"
  },
  "priority": "normal",
  "max_attempts": 3
}
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "job_key": "ADD_PRECEDENT:CASE-2026-001:PREC-001",
  "status": "PENDING",
  "created_at": "2026-03-03T12:00:00Z"
}
```

---

### GET /internal/status/{correlation_id}

Get detailed status for correlation ID.

**Authentication:** HMAC signature

**Response:**
```json
{
  "correlation_id": "DAILY_WATCH:2026-03-03",
  "status": "RUNNING",
  "started_at": "2026-03-03T10:00:00Z",
  "current_stage": "THINK",
  "total_cost_usd": 2.15,
  "total_tokens": 125678,
  "events": [
    {
      "type": "WATCH_START",
      "timestamp": "2026-03-03T10:00:00Z"
    },
    {
      "type": "ITEMS_COLLECTED",
      "timestamp": "2026-03-03T10:05:00Z",
      "count": 12
    }
  ],
  "llm_calls": [
    {
      "stage": "WATCH",
      "calls": 5,
      "cost_usd": 0.45,
      "tokens": 23456
    }
  ]
}
```

---

## Error Codes

### HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request successful |
| 400 | Bad Request | Invalid parameters |
| 401 | Unauthorized | Missing authentication |
| 403 | Forbidden | Invalid signature |
| 404 | Not Found | Resource not found |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |
| 503 | Service Unavailable | System unhealthy |

### Error Response Format

```json
{
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "Invalid value for 'days' parameter",
    "details": {
      "parameter": "days",
      "provided": "abc",
      "expected": "integer between 1 and 365"
    }
  },
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-03-03T12:00:00Z"
}
```

### Common Error Codes

| Code | Description | Resolution |
|------|-------------|------------|
| `INVALID_PARAMETER` | Invalid query parameter | Check API documentation |
| `MISSING_SIGNATURE` | Missing HMAC signature | Add X-Internal-Signature header |
| `INVALID_SIGNATURE` | Invalid HMAC signature | Check shared secret |
| `RATE_LIMIT_EXCEEDED` | Too many requests | Wait and retry (see Retry-After header) |
| `DATABASE_ERROR` | Database error | Check system health |
| `RESOURCE_NOT_FOUND` | Resource not found | Verify resource ID |

---

## Rate Limiting

**Limits:**
- Public endpoints: 1000 requests/hour per IP
- Internal endpoints: No limit (HMAC authenticated)

**Headers:**
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1709470800
Retry-After: 3600
```

---

## CORS

**Allowed Origins:** Configurable via `CORS_ORIGINS` environment variable

**Allowed Methods:** GET, POST, PUT, DELETE, OPTIONS

**Allowed Headers:** Content-Type, Authorization, X-Internal-Signature

---

## Authentication

### HMAC Signature (Internal APIs)

**Algorithm:** HMAC-SHA256

**Header:** `X-Internal-Signature`

**Computation:**
```python
import hmac
import hashlib

signature = hmac.new(
    shared_secret.encode('utf-8'),
    request_body,
    hashlib.sha256
).hexdigest()
```

**Example:**
```python
import requests
import hmac
import hashlib

shared_secret = "your-shared-secret"
body = '{"type": "ADD_PRECEDENT", "payload": {...}}'

signature = hmac.new(
    shared_secret.encode('utf-8'),
    body.encode('utf-8'),
    hashlib.sha256
).hexdigest()

response = requests.post(
    "https://your-app.railway.app/internal/jobs",
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-Internal-Signature": signature
    }
)
```

---

## Webhooks

### Telegram Webhook Setup

```bash
curl -X POST https://api.telegram.org/bot$TOKEN/setWebhook \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app.railway.app/telegram/webhook",
    "secret_token": "your-webhook-secret"
  }'
```

### Webhook Verification

All webhooks verify HMAC signatures before processing.

---

## Client Libraries

### Python

```python
import requests

class SanjaiInsightClient:
    def __init__(self, base_url, api_key=None):
        self.base_url = base_url
        self.api_key = api_key

    def get_health(self):
        response = requests.get(f"{self.base_url}/health")
        return response.json()

    def get_cost(self, days=7):
        response = requests.get(
            f"{self.base_url}/api/cost",
            params={"days": days}
        )
        return response.json()

# Usage
client = SanjaiInsightClient("https://your-app.railway.app")
health = client.get_health()
print(health["status"])
```

---

**Version:** 2.0
**Last Updated:** 2026-03-03
