"""
Approval Handler for Proposal Actions
Processes APPROVE/REJECT/DEFER/DRAFT_ONLY decisions
"""

import json
import logging
from datetime import datetime
from typing import Optional, Tuple
from uuid import uuid4

import aiosqlite

from ..models import ApprovalDecision, EventType
from ..core.events import EventLogger

logger = logging.getLogger(__name__)


class ApprovalHandler:
    """Handles proposal approval events"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.event_logger = EventLogger(db_path)

    async def process_approval(
        self,
        proposal_id: str,
        chat_id: int,
        decision: ApprovalDecision,
        actor: str = "HUMAN",
        note: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Process approval (idempotent via UNIQUE constraint)
        Returns: (success, message)
        """
        try:
            # Insert approval (idempotent)
            approval_id = str(uuid4())

            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO approvals (approval_id, proposal_id, chat_id, decision, actor, note)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        approval_id,
                        proposal_id,
                        chat_id,
                        decision.value,
                        actor,
                        note,
                    ),
                )
                await db.commit()

            # Log event
            await self.event_logger.log(
                EventType.APPROVAL_RECEIVED,
                f"PROPOSAL:{proposal_id}",
                {
                    "proposal_id": proposal_id,
                    "approval_id": approval_id,
                    "decision": decision.value,
                    "actor": actor,
                },
            )

            # If APPROVE, execute actions
            if decision == ApprovalDecision.APPROVE:
                await self._execute_proposal_actions(proposal_id)

            return (True, f"Approval recorded: {decision.value}")

        except aiosqlite.IntegrityError:
            # Already processed (duplicate click)
            logger.warning(f"Duplicate approval for proposal {proposal_id} by chat {chat_id}")
            return (False, "Already processed (duplicate)")

        except Exception as e:
            logger.error(f"Failed to process approval: {e}")
            return (False, f"Error: {str(e)}")

    async def _execute_proposal_actions(self, proposal_id: str) -> None:
        """Execute approved actions"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Get actions that require approval
            cursor = await db.execute(
                """
                SELECT * FROM proposal_actions
                WHERE proposal_id = ? AND requires_approval = 1 AND executed = 0
                """,
                (proposal_id,),
            )
            actions = await cursor.fetchall()

            for action in actions:
                try:
                    # Execute action (placeholder - actual execution depends on action_type)
                    logger.info(
                        f"Executing action: {action['action_type']} for proposal {proposal_id}"
                    )

                    # Mark as executed
                    await db.execute(
                        """
                        UPDATE proposal_actions
                        SET executed = 1, executed_at = ?
                        WHERE id = ?
                        """,
                        (datetime.now().isoformat(), action["id"]),
                    )

                    # Log event
                    await self.event_logger.log(
                        EventType.ACTION_EXECUTED,
                        f"PROPOSAL:{proposal_id}",
                        {
                            "action_id": action["id"],
                            "action_type": action["action_type"],
                        },
                    )

                except Exception as e:
                    logger.error(f"Failed to execute action {action['id']}: {e}")

            await db.commit()

    async def get_proposal_decision(self, proposal_id: str) -> Optional[str]:
        """Get latest decision for proposal"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT decision FROM approvals
                WHERE proposal_id = ?
                ORDER BY decided_at DESC
                LIMIT 1
                """,
                (proposal_id,),
            )
            row = await cursor.fetchone()
            return row["decision"] if row else None
