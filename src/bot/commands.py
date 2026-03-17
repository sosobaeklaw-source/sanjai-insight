"""
Telegram Bot Commands Setup
봇 명령어 등록 및 초기화
"""

import logging
import os

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
)

from .handlers import TelegramHandlers

logger = logging.getLogger(__name__)


def setup_bot_application(db_path: str) -> Application:
    """
    Telegram 봇 애플리케이이션 초기화

    Args:
        db_path: 데이터베이스 경로

    Returns:
        Telegram Application
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not configured")

    # Application 생성
    application = Application.builder().token(token).build()

    # Handlers 초기화
    handlers = TelegramHandlers(db_path)

    # 명령어 등록
    application.add_handler(
        CommandHandler("status", handlers.handle_status_command)
    )
    application.add_handler(
        CommandHandler("cost", handlers.handle_cost_command)
    )
    application.add_handler(
        CommandHandler("health", handlers.handle_health_command)
    )

    # Callback query 핸들러 (버튼 클릭)
    application.add_handler(
        CallbackQueryHandler(handlers.handle_callback_query)
    )

    logger.info("[Bot] Telegram bot application initialized")

    return application


async def start_bot(db_path: str):
    """
    Telegram 봇 시작 (webhook 또는 polling)

    Args:
        db_path: 데이터베이스 경로
    """
    application = setup_bot_application(db_path)

    # Webhook 모드 (Railway 등 프로덕션)
    webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL")
    if webhook_url:
        logger.info(f"[Bot] Starting in webhook mode: {webhook_url}")
        await application.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", "8080")),
            url_path=os.getenv("TELEGRAM_WEBHOOK_PATH", "/telegram"),
            webhook_url=webhook_url,
        )
    else:
        # Polling 모드 (로컬 개발)
        logger.info("[Bot] Starting in polling mode")
        await application.run_polling()
