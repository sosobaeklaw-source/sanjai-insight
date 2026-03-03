#!/usr/bin/env python3
"""
Telegram 봇 통합 테스트
========================
"""

import pytest
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ============================================================================
# Test Configuration
# ============================================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "test_token")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CEO_CHAT_ID", "123456789")


# ============================================================================
# Telegram Integration Tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("TELEGRAM_BOT_TOKEN"), reason="No Telegram token")
async def test_telegram_send_message():
    """TELEGRAM-001: 메시지 전송"""
    from telegram import Bot

    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    message = await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text="[테스트] sanjai-insight 통합 테스트"
    )

    assert message.text == "[테스트] sanjai-insight 통합 테스트"


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("TELEGRAM_BOT_TOKEN"), reason="No Telegram token")
async def test_telegram_send_with_buttons():
    """TELEGRAM-002: 버튼 포함 메시지"""
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    keyboard = [
        [
            InlineKeyboardButton("✅ 승인", callback_data="approve:test"),
            InlineKeyboardButton("❌ 거절", callback_data="reject:test")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text="[테스트] 승인/거절 버튼 테스트",
        reply_markup=reply_markup
    )

    assert message.reply_markup is not None


@pytest.mark.asyncio
async def test_telegram_callback_parsing():
    """TELEGRAM-003: 콜백 데이터 파싱"""
    callback_data = "approve:insight_123"

    action, insight_id = callback_data.split(":", 1)

    assert action == "approve"
    assert insight_id == "insight_123"


@pytest.mark.asyncio
async def test_telegram_message_formatting():
    """TELEGRAM-004: 메시지 포맷팅"""
    from datetime import datetime

    insight_data = {
        "title": "테스트 인사이트",
        "summary": "요약 내용",
        "confidence": 0.85,
        "category": "policy"
    }

    message = f"""
🔍 **새로운 인사이트**

**제목:** {insight_data['title']}
**카테고리:** {insight_data['category']}
**신뢰도:** {insight_data['confidence']:.0%}

**요약:**
{insight_data['summary']}

**생성일시:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
    """.strip()

    assert "테스트 인사이트" in message
    assert "85%" in message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
