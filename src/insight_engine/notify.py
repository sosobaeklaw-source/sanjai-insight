from __future__ import annotations

import httpx

from .config import RuntimeConfig
from .models import DraftDocument, PublishArtifact


def build_notification_message(drafts: list[DraftDocument], run_id: str) -> str:
    lines = [
        f"[insight-engine] run_id={run_id}",
        f"초안 {len(drafts)}건이 생성되었습니다.",
    ]
    for draft in drafts:
        lines.append(f"- {draft.title}")
    lines.append("검토 후 공개 여부만 결정하면 됩니다.")
    return "\n".join(lines)


def notify_telegram(
    config: RuntimeConfig,
    drafts: list[DraftDocument],
    run_id: str,
    dry_run: bool,
) -> PublishArtifact:
    if not (config.telegram_bot_token and config.notify_chat_id):
        return PublishArtifact(
            target="telegram",
            mode="message",
            location="",
            status="missing_config",
        )

    message = build_notification_message(drafts, run_id)
    if dry_run:
        return PublishArtifact(
            target="telegram",
            mode="message",
            location="preview",
            status="skipped_dry_run",
            metadata={"preview": message},
        )

    response = httpx.post(
        f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage",
        json={"chat_id": config.notify_chat_id, "text": message},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return PublishArtifact(
        target="telegram",
        mode="message",
        location=str(payload.get("result", {}).get("message_id", "")),
        status="sent",
    )
