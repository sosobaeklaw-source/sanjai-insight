"""
sanjai-agent Client with Zero-Trust Security
HMAC-SHA256 signature + allowlist + audit logging
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


class AgentClient:
    """Zero-trust client for sanjai-agent"""

    # Allowlist of permitted job types
    ALLOWED_JOB_TYPES = {
        "ADD_PRECEDENT_TO_CASE",
        "RUN_LEGAL_DRAFTER",
        "GENERATE_LEAD_FROM_INSIGHT",
        "UPDATE_CASE_STRATEGY",
    }

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.event_logger = EventLogger(db_path)

        # Get configuration from environment
        self.agent_url = os.getenv("SANJAI_AGENT_URL", "http://localhost:8000")
        self.shared_secret = os.getenv("INSIGHT_TO_AGENT_SECRET")

        if not self.shared_secret:
            logger.warning("INSIGHT_TO_AGENT_SECRET not configured. Agent calls disabled.")
            self.enabled = False
        else:
            self.enabled = True

    async def send_request(
        self,
        proposal_id: str,
        job_type: str,
        payload: Dict[str, Any],
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Send request to sanjai-agent
        Returns: (success, request_id, response)
        """
        if not self.enabled:
            return (False, None, {"error": "Agent client disabled"})

        # Security: Allowlist check
        if job_type not in self.ALLOWED_JOB_TYPES:
            logger.error(f"Job type not in allowlist: {job_type}")
            return (False, None, {"error": f"Job type not allowed: {job_type}"})

        # Create request
        request_id = str(uuid4())
        request_body = {
            "request_id": request_id,
            "proposal_id": proposal_id,
            "job_type": job_type,
            "payload": payload,
            "requested_at": datetime.now().isoformat(),
        }

        # Calculate payload hash
        body_json = json.dumps(request_body, sort_keys=True, ensure_ascii=False)
        payload_hash = hashlib.sha256(body_json.encode("utf-8")).hexdigest()

        # Generate HMAC signature
        signature = self._generate_signature(body_json)

        # Store request in DB (audit trail)
        await self._store_request(
            request_id,
            proposal_id,
            job_type,
            payload_hash,
            signature,
        )

        # Send HTTP request
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.agent_url}/external/jobs",
                    json=request_body,
                    headers={
                        "X-Sanjai-Signature": signature,
                        "Content-Type": "application/json",
                    },
                )

                response.raise_for_status()
                response_data = response.json()

                # Update request status
                await self._update_request_status(request_id, "ACK", response_data)

                # Log event
                await self.event_logger.log(
                    EventType.ACTION_EXECUTED,
                    f"PROPOSAL:{proposal_id}",
                    {
                        "request_id": request_id,
                        "job_type": job_type,
                        "status": "ACK",
                    },
                )

                return (True, request_id, response_data)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling agent: {e}")
            await self._update_request_status(request_id, "FAILED", {"error": str(e)})
            return (False, request_id, {"error": str(e)})

        except Exception as e:
            logger.error(f"Failed to call agent: {e}")
            await self._update_request_status(request_id, "FAILED", {"error": str(e)})
            return (False, request_id, {"error": str(e)})

    def _generate_signature(self, body: str) -> str:
        """Generate HMAC-SHA256 signature"""
        return hmac.new(
            self.shared_secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def _store_request(
        self,
        request_id: str,
        proposal_id: str,
        job_type: str,
        payload_hash: str,
        signature: str,
    ) -> None:
        """Store request in audit trail"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO external_requests
                (request_id, proposal_id, target_system, job_type, payload_hash, signature, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    proposal_id,
                    "SANJAI_AGENT",
                    job_type,
                    payload_hash,
                    signature,
                    "PENDING",
                ),
            )
            await db.commit()

    async def _update_request_status(
        self,
        request_id: str,
        status: str,
        response: Optional[Dict] = None,
    ) -> None:
        """Update request status"""
        async with aiosqlite.connect(self.db_path) as db:
            if response:
                await db.execute(
                    """
                    UPDATE external_requests
                    SET status = ?, response_json = ?, sent_at = ?
                    WHERE request_id = ?
                    """,
                    (
                        status,
                        json.dumps(response, ensure_ascii=False),
                        datetime.now().isoformat(),
                        request_id,
                    ),
                )
            else:
                await db.execute(
                    """
                    UPDATE external_requests
                    SET status = ?
                    WHERE request_id = ?
                    """,
                    (status, request_id),
                )

            await db.commit()

    async def get_request_status(self, request_id: str) -> Optional[Dict]:
        """Get request status"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM external_requests WHERE request_id = ?",
                (request_id,),
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return {
                "request_id": row["request_id"],
                "proposal_id": row["proposal_id"],
                "job_type": row["job_type"],
                "status": row["status"],
                "response_json": json.loads(row["response_json"]) if row["response_json"] else None,
                "created_at": row["created_at"],
                "sent_at": row["sent_at"],
            }
