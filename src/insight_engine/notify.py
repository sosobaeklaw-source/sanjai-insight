from __future__ import annotations

import httpx

from .config import RuntimeConfig
from .models import DraftDocument, PublishArtifact


def build_notification_message(
    drafts: list[DraftDocument],
    run_id: str,
    wp_urls: dict[str, str] | None = None,
) -> str:
    lines = [
        f"[insight-engine] {run_id}",
        f"초안 {len(drafts)}건이 생성되었습니다.",
        "",
    ]
    for draft in drafts:
        line = f"• {draft.title}"
        if wp_urls and draft.slug in wp_urls:
            line += f"\n  {wp_urls[draft.slug]}"
        lines.append(line)
    lines.extend([
        "",
        "검토 후 공개 여부만 결정하면 됩니다.",
    ])
    return "\n".join(lines)


def send_telegram(token: str, chat_id: str, text: str) -> dict | None:
    """Send a message via Telegram Bot API. Returns API result or None."""
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("result")
    except Exception:
        return None


def notify_telegram(
    config: RuntimeConfig,
    drafts: list[DraftDocument],
    run_id: str,
    dry_run: bool,
    wp_urls: dict[str, str] | None = None,
) -> PublishArtifact:
    if not (config.telegram_bot_token and config.notify_chat_id):
        return PublishArtifact(
            target="telegram",
            mode="message",
            location="",
            status="missing_config",
        )

    message = build_notification_message(drafts, run_id, wp_urls=wp_urls)
    if dry_run:
        return PublishArtifact(
            target="telegram",
            mode="message",
            location="preview",
            status="skipped_dry_run",
            metadata={"preview": message},
        )

    result = send_telegram(config.telegram_bot_token, config.notify_chat_id, message)
    if result is None:
        return PublishArtifact(
            target="telegram",
            mode="message",
            location="",
            status="send_failed",
        )

    return PublishArtifact(
        target="telegram",
        mode="message",
        location=str(result.get("message_id", "")),
        status="sent",
    )
