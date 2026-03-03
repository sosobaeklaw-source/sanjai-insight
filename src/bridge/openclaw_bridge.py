"""
OpenClaw Bridge - Integration with OpenClaw Legal Drafting Service
Zero-trust architecture with HMAC-SHA256 signature and audit trail
"""

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

import aiosqlite
import httpx

from ..models import EventType
from ..core.events import EventLogger

logger = logging.getLogger(__name__)


class OpenClawBridge:
    """Zero-trust bridge to OpenClaw service"""

    # Allowlist of permitted operations
    ALLOWED_OPERATIONS = {
        "DRAFT_DOCUMENT",
        "REVIEW_DOCUMENT",
        "EXTRACT_PRECEDENTS",
        "GENERATE_BRIEF",
    }

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.event_logger = EventLogger(db_path)

        # Get configuration from environment
        self.openclaw_url = os.getenv("OPENCLAW_URL", "http://localhost:8001")
        self.shared_secret = os.getenv("INSIGHT_TO_OPENCLAW_SECRET")

        if not self.shared_secret:
            logger.warning("INSIGHT_TO_OPENCLAW_SECRET not configured. OpenClaw calls disabled.")
            self.enabled = False
        else:
            self.enabled = True

    async def call(
        self,
        operation: str,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Call OpenClaw service

        Args:
            operation: Operation type (must be in ALLOWED_OPERATIONS)
            payload: Operation-specific payload
            correlation_id: Optional correlation ID for tracking

        Returns:
            (success, request_id, response)
        """
        if not self.enabled:
            return (False, None, {"error": "OpenClaw bridge disabled"})

        # Security: Allowlist check
        if operation not in self.ALLOWED_OPERATIONS:
            logger.error(f"Operation not in allowlist: {operation}")
            return (False, None, {"error": f"Operation not allowed: {operation}"})

        # Create request
        request_id = str(uuid4())
        request_body = {
            "request_id": request_id,
            "operation": operation,
            "payload": payload,
            "correlation_id": correlation_id or str(uuid4()),
            "requested_at": datetime.now().isoformat(),
        }

        # Calculate payload hash
        body_json = json.dumps(request_body, sort_keys=True, ensure_ascii=False)
        payload_hash = hashlib.sha256(body_json.encode("utf-8")).hexdigest()

        # Generate HMAC signature
        signature = hmac.new(
            self.shared_secret.encode("utf-8"),
            payload_hash.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # Log request to audit trail
        await self._log_request(
            request_id=request_id,
            operation=operation,
            payload_hash=payload_hash,
            signature=signature,
        )

        # Send HTTP request
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.openclaw_url}/api/v1/operations",
                    json=request_body,
                    headers={
                        "X-Request-ID": request_id,
                        "X-Signature": signature,
                        "X-Payload-Hash": payload_hash,
                        "Content-Type": "application/json",
                    },
                )

                response.raise_for_status()
                response_data = response.json()

                # Log success
                await self._log_response(
                    request_id=request_id,
                    status_code=response.status_code,
                    success=True,
                    response_data=response_data,
                )

                logger.info(
                    f"[OpenClaw] Operation {operation} succeeded: {request_id}"
                )

                return (True, request_id, response_data)

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            logger.error(f"[OpenClaw] HTTP error: {error_msg}")

            await self._log_response(
                request_id=request_id,
                status_code=e.response.status_code,
                success=False,
                response_data={"error": error_msg},
            )

            return (False, request_id, {"error": error_msg})

        except Exception as e:
            error_msg = f"Request failed: {str(e)}"
            logger.error(f"[OpenClaw] Error: {error_msg}")

            await self._log_response(
                request_id=request_id,
                status_code=0,
                success=False,
                response_data={"error": error_msg},
            )

            return (False, request_id, {"error": error_msg})

    async def _log_request(
        self,
        request_id: str,
        operation: str,
        payload_hash: str,
        signature: str,
    ):
        """Log request to external_requests table"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO external_requests
                (request_id, service, operation, payload_hash, signature, status)
                VALUES (?, 'OPENCLAW', ?, ?, ?, 'PENDING')
                """,
                (request_id, operation, payload_hash, signature),
            )
            await db.commit()

    async def _log_response(
        self,
        request_id: str,
        status_code: int,
        success: bool,
        response_data: Optional[Dict],
    ):
        """Update request with response"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE external_requests
                SET
                    status = ?,
                    status_code = ?,
                    response_json = ?,
                    responded_at = datetime('now')
                WHERE request_id = ?
                """,
                (
                    "SUCCESS" if success else "FAILED",
                    status_code,
                    json.dumps(response_data) if response_data else None,
                    request_id,
                ),
            )
            await db.commit()

    async def draft_document(
        self,
        template_type: str,
        context: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Draft a legal document using OpenClaw

        Args:
            template_type: Document template type (e.g., "BRIEF", "COMPLAINT", "MEMO")
            context: Context variables for template
            correlation_id: Optional correlation ID

        Returns:
            (success, request_id, response with drafted document)
        """
        payload = {
            "template_type": template_type,
            "context": context,
        }
        return await self.call("DRAFT_DOCUMENT", payload, correlation_id)

    async def extract_precedents(
        self,
        query: str,
        limit: int = 10,
        correlation_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Extract relevant precedents from OpenClaw

        Args:
            query: Search query for precedents
            limit: Maximum number of results
            correlation_id: Optional correlation ID

        Returns:
            (success, request_id, response with precedents)
        """
        payload = {
            "query": query,
            "limit": limit,
        }
        return await self.call("EXTRACT_PRECEDENTS", payload, correlation_id)

    async def generate_brief(
        self,
        case_facts: Dict[str, Any],
        legal_issues: list[str],
        correlation_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Generate a legal brief using OpenClaw

        Args:
            case_facts: Case facts and details
            legal_issues: List of legal issues to address
            correlation_id: Optional correlation ID

        Returns:
            (success, request_id, response with generated brief)
        """
        payload = {
            "case_facts": case_facts,
            "legal_issues": legal_issues,
        }
        return await self.call("GENERATE_BRIEF", payload, correlation_id)
