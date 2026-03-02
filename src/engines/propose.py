"""
Propose Engine - 제안 생성 및 Telegram 전송
4블록 템플릿 + 승인 버튼
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aiosqlite
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..models import EventType
from ..core.events import EventLogger
from ..core.checkpoint import CheckpointManager
from ..core.termination import TerminationChecker

logger = logging.getLogger(__name__)


class ProposeEngine:
    """Propose Engine - 인사이트 기반 제안 생성"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.event_logger = EventLogger(db_path)

    async def run(
        self,
        correlation_id: str,
        payload: Dict[str, Any],
        ctx: Dict[str, Any],
        checker: TerminationChecker,
        checkpoint_manager: CheckpointManager,
        event_logger: EventLogger,
    ) -> Dict[str, Any]:
        """
        Propose 실행 (Worker 핸들러)

        Args:
            correlation_id: 실행 추적 ID
            payload: {min_confidence: 0.7}
            ctx: 체크포인트 컨텍스트
            checker: 종료 조건 체크
            checkpoint_manager: 체크포인트 관리
            event_logger: 이벤트 로거

        Returns:
            {proposals_created: int, proposals_sent: int}
        """
        min_confidence = payload.get("min_confidence", 0.7)

        # 시작 이벤트
        await event_logger.log(
            EventType.PROPOSE_START,
            correlation_id,
            {"min_confidence": min_confidence},
        )

        # 인사이트 로드 (NEW 상태 + confidence >= min)
        insights = await self._load_insights(correlation_id, min_confidence)
        logger.info(f"[Propose] Loaded {len(insights)} insights")

        if not insights:
            await event_logger.log(
                EventType.PROPOSE_END,
                correlation_id,
                {"proposals_created": 0, "reason": "no_insights"},
            )
            return {"proposals_created": 0, "proposals_sent": 0}

        proposals_created = 0
        proposals_sent = 0

        for insight in insights:
            # 종료 조건 체크
            should_terminate, reason = checker.check()
            if should_terminate:
                logger.warning(f"[Propose] Termination: {reason}")
                await event_logger.log(
                    EventType.TERMINATION,
                    correlation_id,
                    {"reason": reason, "stage": "PROPOSE"},
                )
                break

            try:
                # 제안 생성
                proposal = await self._create_proposal(insight, correlation_id)
                proposals_created += 1

                # Telegram 전송 (선택적)
                telegram_bot = payload.get("telegram_bot")
                chat_id = payload.get("chat_id")

                if telegram_bot and chat_id:
                    sent = await self._send_telegram_message(
                        telegram_bot, chat_id, proposal, insight
                    )
                    if sent:
                        proposals_sent += 1

                # 이벤트 기록
                await event_logger.log(
                    EventType.PROPOSAL_SENT,
                    correlation_id,
                    {"proposal_id": proposal["id"], "insight_id": insight["id"]},
                )

                # 인사이트 상태 업데이트
                await self._update_insight_status(insight["id"], "PROPOSED")

                # 체크포인트 저장
                ctx["propose_progress"] = {
                    "proposals_created": proposals_created,
                    "proposals_sent": proposals_sent,
                }
                await checkpoint_manager.save(correlation_id, "PROPOSE", ctx)

            except Exception as e:
                logger.error(f"[Propose] Error processing insight {insight['id']}: {e}")
                await event_logger.log(
                    EventType.ERROR,
                    correlation_id,
                    {"error": str(e), "insight_id": insight["id"], "stage": "PROPOSE"},
                )
                continue

        # 완료 이벤트
        await event_logger.log(
            EventType.PROPOSE_END,
            correlation_id,
            {
                "proposals_created": proposals_created,
                "proposals_sent": proposals_sent,
            },
        )

        return {
            "proposals_created": proposals_created,
            "proposals_sent": proposals_sent,
        }

    async def _load_insights(
        self, correlation_id: str, min_confidence: float
    ) -> List[Dict[str, Any]]:
        """
        인사이트 로드 (NEW 상태 + confidence >= min)
        """
        insights = []

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # correlation_id로 생성된 인사이트 조회
            # (실제로는 events 테이블에서 INSIGHT_CREATED 이벤트 추적)
            cursor = await db.execute(
                """
                SELECT i.* FROM insights i
                WHERE i.status = 'NEW'
                  AND i.confidence >= ?
                  AND i.created_at >= datetime('now', '-1 day')
                ORDER BY i.confidence DESC, i.created_at DESC
                LIMIT 10
                """,
                (min_confidence,),
            )
            rows = await cursor.fetchall()

            for row in rows:
                insights.append(dict(row))

        return insights

    async def _create_proposal(
        self, insight: Dict[str, Any], correlation_id: str
    ) -> Dict[str, Any]:
        """
        제안 생성 (4블록 템플릿)
        """
        proposal_id = str(uuid4())

        # 인사이트 claims 로드
        claims = await self._load_claims(insight["id"])

        # 메시지 생성 (4블록)
        message = self._format_proposal_message(insight, claims)

        # DB 저장
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO proposals (id, insight_id, message_text, response)
                VALUES (?, ?, ?, ?)
                """,
                (proposal_id, insight["id"], message, "PENDING"),
            )
            await db.commit()

        proposal = {
            "id": proposal_id,
            "insight_id": insight["id"],
            "message_text": message,
        }

        return proposal

    async def _load_claims(self, insight_id: str) -> List[Dict[str, Any]]:
        """Claims 로드"""
        claims = []

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM insight_claims WHERE insight_id = ?",
                (insight_id,),
            )
            rows = await cursor.fetchall()

            for row in rows:
                claims.append(
                    {
                        "text": row["text"],
                        "evidence_ids": json.loads(row["evidence_ids_json"]),
                    }
                )

        return claims

    def _format_proposal_message(
        self, insight: Dict[str, Any], claims: List[Dict[str, Any]]
    ) -> str:
        """
        제안 메시지 포맷 (4블록 템플릿)

        블록 1: 요약
        블록 2: 근거
        블록 3: 제안 액션
        블록 4: 버튼 (승인/초안만/보류/거절)
        """
        # 블록 1: 요약
        title = insight.get("title", "제목 없음")
        urgency = insight.get("urgency", "MEDIUM")
        confidence = insight.get("confidence", 0.0)

        urgency_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(urgency, "⚪")

        summary = f"""
📊 **인사이트 제안**

{urgency_emoji} **{title}**
신뢰도: {confidence:.0%} | 긴급도: {urgency}
"""

        # 블록 2: 근거
        evidence_section = "\n📋 **근거:**\n"
        for i, claim in enumerate(claims[:3], 1):  # 최대 3개
            evidence_ids = claim["evidence_ids"]
            evidence_section += f"{i}. {claim['text']}\n"
            evidence_section += f"   증거: {', '.join(evidence_ids[:3])}\n"

        # 블록 3: 제안 액션
        actions = insight.get("suggested_actions", [])
        if isinstance(actions, str):
            actions = json.loads(actions)

        action_section = "\n🎯 **제안 액션:**\n"
        for i, action in enumerate(actions[:3], 1):  # 최대 3개
            action_section += f"{i}. {action}\n"

        # 조합
        message = summary + evidence_section + action_section

        return message.strip()

    async def _send_telegram_message(
        self,
        bot,
        chat_id: int,
        proposal: Dict[str, Any],
        insight: Dict[str, Any],
    ) -> bool:
        """
        Telegram 메시지 전송 (버튼 포함)
        """
        try:
            # 버튼 생성
            keyboard = [
                [
                    InlineKeyboardButton(
                        "✅ 승인", callback_data=f"approve:{proposal['id']}"
                    ),
                    InlineKeyboardButton(
                        "📝 초안만", callback_data=f"draft:{proposal['id']}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "⏸️ 보류", callback_data=f"defer:{proposal['id']}"
                    ),
                    InlineKeyboardButton(
                        "❌ 거절", callback_data=f"reject:{proposal['id']}"
                    ),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # 메시지 전송
            await bot.send_message(
                chat_id=chat_id,
                text=proposal["message_text"],
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )

            logger.info(f"[Propose] Sent proposal {proposal['id']} to chat {chat_id}")
            return True

        except Exception as e:
            logger.error(f"[Propose] Failed to send Telegram message: {e}")
            return False

    async def _update_insight_status(self, insight_id: str, status: str):
        """인사이트 상태 업데이트"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE insights SET status = ? WHERE id = ?",
                (status, insight_id),
            )
            await db.commit()
