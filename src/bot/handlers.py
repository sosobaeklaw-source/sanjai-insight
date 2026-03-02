"""
Telegram Bot Handlers
callback_query 처리 + 승인/거절 로직
"""

import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from ..bot.idempotency import TelegramIdempotency
from ..bot.approval_handler import ApprovalHandler
from ..models import ApprovalDecision

logger = logging.getLogger(__name__)


class TelegramHandlers:
    """Telegram 봇 핸들러"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.idempotency = TelegramIdempotency(db_path)
        self.approval_handler = ApprovalHandler(db_path)

    async def handle_callback_query(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """
        Callback query 처리 (버튼 클릭)

        callback_data 형식: "action:proposal_id"
        - approve:P123
        - draft:P123
        - defer:P123
        - reject:P123
        """
        query = update.callback_query
        await query.answer()  # 로딩 표시 제거

        # 멱등성 체크
        update_id = update.update_id
        chat_id = query.message.chat_id
        is_new = await self.idempotency.mark_processed(
            update_id, chat_id, {"callback_data": query.data}
        )

        if not is_new:
            logger.info(f"[Bot] Duplicate callback_query: {update_id}")
            await query.edit_message_text(
                text=f"{query.message.text}\n\n⚠️ 이미 처리된 요청입니다.",
                parse_mode="Markdown",
            )
            return

        # callback_data 파싱
        try:
            action, proposal_id = query.data.split(":", 1)
        except ValueError:
            logger.error(f"[Bot] Invalid callback_data: {query.data}")
            await query.edit_message_text(
                text=f"{query.message.text}\n\n❌ 잘못된 요청 형식입니다."
            )
            return

        # 액션 매핑
        decision_map = {
            "approve": ApprovalDecision.APPROVE,
            "draft": ApprovalDecision.DRAFT_ONLY,
            "defer": ApprovalDecision.DEFER,
            "reject": ApprovalDecision.REJECT,
        }

        decision = decision_map.get(action)
        if not decision:
            logger.error(f"[Bot] Unknown action: {action}")
            await query.edit_message_text(
                text=f"{query.message.text}\n\n❌ 알 수 없는 액션입니다."
            )
            return

        # 승인 처리
        success, message = await self.approval_handler.process_approval(
            proposal_id=proposal_id,
            chat_id=chat_id,
            decision=decision,
            actor="HUMAN",
            note=f"Callback query: {query.data}",
        )

        # 결과 메시지
        if success:
            emoji_map = {
                ApprovalDecision.APPROVE: "✅",
                ApprovalDecision.DRAFT_ONLY: "📝",
                ApprovalDecision.DEFER: "⏸️",
                ApprovalDecision.REJECT: "❌",
            }
            emoji = emoji_map.get(decision, "✔️")

            await query.edit_message_text(
                text=f"{query.message.text}\n\n{emoji} **{decision.value}** 처리 완료",
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text(
                text=f"{query.message.text}\n\n❌ 처리 실패: {message}"
            )

    async def handle_status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """
        /status 명령어 핸들러
        사용법: /status <correlation_id>
        """
        from ..api.status import get_status

        args = context.args
        if not args:
            await update.message.reply_text(
                "사용법: /status <correlation_id>\n"
                "예: /status DAILY_WATCH:2026-03-03"
            )
            return

        correlation_id = args[0]
        status = await get_status(self.db_path, correlation_id)

        if not status:
            await update.message.reply_text(f"❌ 실행 기록을 찾을 수 없습니다: {correlation_id}")
            return

        # 포맷팅
        message = f"""
📊 **실행 상태**

🆔 Run ID: `{status.run_id}`
📌 Correlation: `{status.correlation_id}`
🔄 상태: {status.status}
📅 시작: {status.started_at.strftime("%Y-%m-%d %H:%M")}
⏱️ 종료: {status.ended_at.strftime("%Y-%m-%d %H:%M") if status.ended_at else "진행중"}

📜 이벤트: {status.event_count}개
💡 인사이트: {status.insights_count}개
📦 수집 아이템: {status.items_collected}개

💰 비용: ${status.total_cost_usd:.4f}
"""

        if status.errors:
            message += f"\n⚠️ **에러:**\n"
            for error in status.errors[:3]:
                message += f"  • {error[:100]}\n"

        await update.message.reply_text(message, parse_mode="Markdown")

    async def handle_cost_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """
        /cost 명령어 핸들러
        사용법: /cost <correlation_id>
        """
        from ..api.cost import get_cost

        args = context.args
        if not args:
            await update.message.reply_text(
                "사용법: /cost <correlation_id>\n"
                "예: /cost DAILY_WATCH:2026-03-03"
            )
            return

        correlation_id = args[0]
        cost = await get_cost(self.db_path, correlation_id)

        if not cost:
            await update.message.reply_text(f"❌ 비용 정보를 찾을 수 없습니다: {correlation_id}")
            return

        # 포맷팅
        message = f"""
💰 **비용 리포트**

🆔 Correlation: `{cost.correlation_id}`
💵 총 비용: ${cost.total_cost_usd:.4f}
🪙 총 토큰: {cost.total_tokens_in + cost.total_tokens_out:,}
  ↗️ Input: {cost.total_tokens_in:,}
  ↘️ Output: {cost.total_tokens_out:,}
🔄 호출 횟수: {cost.call_count}회

⏱️ 평균 지연: {cost.avg_latency_ms:.0f}ms

📊 **단계별 비용:**
"""

        for stage, stage_cost in cost.by_stage.items():
            message += f"  • {stage}: ${stage_cost:.4f}\n"

        message += "\n🤖 **모델별 비용:**\n"
        for model, model_cost in cost.by_model.items():
            model_name = model.split("/")[-1][:30]
            message += f"  • {model_name}: ${model_cost:.4f}\n"

        await update.message.reply_text(message, parse_mode="Markdown")

    async def handle_health_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """
        /health 명령어 핸들러
        """
        from ..api.health import get_health
        import os

        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        health = await get_health(self.db_path, telegram_token)

        # 포맷팅
        status_emoji = "✅" if health.db_connected else "❌"

        message = f"""
{status_emoji} **시스템 상태**

🗄️ DB 연결: {"✅" if health.db_connected else "❌"}
📝 WAL 모드: {"✅" if health.db_wal_enabled else "❌"}
🤖 Telegram: {"✅" if health.telegram_configured else "❌"}
📦 Vault: {"✅" if health.vault_accessible else "❌"}

📊 **24시간 메트릭:**
💡 인사이트: {health.insights_24h}개
📋 대기 제안: {health.pending_proposals}개
💰 비용: ${health.cost_24h_usd:.4f}

⏰ 마지막 성공 실행:
{health.last_success_run.strftime("%Y-%m-%d %H:%M") if health.last_success_run else "없음"}

🔄 작업 상태:
  • 대기: {health.pending_jobs}개
  • 실행중: {health.running_jobs}개
"""

        await update.message.reply_text(message, parse_mode="Markdown")
