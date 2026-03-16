"""Telegram approval workflow for draft review before publishing."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import RuntimeConfig
from .models import DraftDocument, PublishArtifact

logger = logging.getLogger(__name__)

# Callback data prefixes — kept short for Telegram's 64-byte limit.
CB_APPROVE = "approve"
CB_REVISE = "revise"
CB_CANCEL = "cancel"

MAX_REVISIONS = 3
POLL_INTERVAL_S = 5
POLL_TIMEOUT_S = 300  # 5 minutes


@dataclass(slots=True)
class ApprovalDecision:
    """Result returned by the approval loop for a single draft."""

    action: str  # "approved" | "cancelled" | "timeout" | "error"
    draft: DraftDocument
    revision_count: int = 0
    feedback: str = ""


class TelegramApproval:
    """Interactive Telegram approval flow for insight drafts.

    Sends a draft preview with inline-keyboard buttons (approve / revise /
    cancel), then polls ``getUpdates`` for the boss's response.  If *revise*
    is chosen the user supplies free-text feedback, Claude rewrites the draft,
    and a new preview is sent.
    """

    def __init__(
        self,
        config: RuntimeConfig,
        *,
        poll_interval: int = POLL_INTERVAL_S,
        poll_timeout: int = POLL_TIMEOUT_S,
    ) -> None:
        self.token = config.telegram_bot_token
        self.chat_id = config.notify_chat_id
        self.anthropic_api_key = config.anthropic_api_key
        self.sonnet_model = config.sonnet_model
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self._base = f"https://api.telegram.org/bot{self.token}"

    # ------------------------------------------------------------------
    # Low-level Telegram helpers
    # ------------------------------------------------------------------

    def _tg_post(self, method: str, payload: dict[str, Any]) -> dict | None:
        """POST to Telegram Bot API.  Returns the ``result`` key or None."""
        try:
            resp = httpx.post(
                f"{self._base}/{method}",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("ok"):
                return body.get("result")
            logger.warning("Telegram %s not ok: %s", method, body)
        except Exception:
            logger.warning("Telegram %s failed", method, exc_info=True)
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_preview(self, draft: DraftDocument, run_id: str) -> int | None:
        """Send a draft preview with inline approve/revise/cancel buttons.

        Returns the ``message_id`` of the sent message, or ``None`` on
        failure.
        """
        # Trim body to Telegram's 4096-char limit (leave room for title).
        max_body = 3600
        body_preview = draft.body[:max_body]
        if len(draft.body) > max_body:
            body_preview += "\n\n... (이하 생략)"

        text = (
            f"<b>{draft.title}</b>\n"
            f"persona: {draft.persona} | run: {run_id}\n\n"
            f"{body_preview}"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "승인", "callback_data": f"{CB_APPROVE}:{draft.slug}"},
                    {"text": "수정 요청", "callback_data": f"{CB_REVISE}:{draft.slug}"},
                    {"text": "취소", "callback_data": f"{CB_CANCEL}:{draft.slug}"},
                ]
            ]
        }

        result = self._tg_post(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": keyboard,
            },
        )
        if result is None:
            return None
        return result.get("message_id")

    def wait_for_response(
        self,
        slug: str,
        *,
        offset: int = 0,
    ) -> tuple[str, str, int]:
        """Poll ``getUpdates`` until a callback or text reply arrives.

        Returns ``(action, feedback_text, new_offset)``.

        *action* is one of ``"approved"``, ``"revise"``, ``"cancelled"``,
        or ``"timeout"``.
        """
        deadline = time.monotonic() + self.poll_timeout

        while time.monotonic() < deadline:
            updates = self._tg_post(
                "getUpdates",
                {"offset": offset, "timeout": min(self.poll_interval, 30)},
            )
            if not updates:
                time.sleep(self.poll_interval)
                continue

            for update in updates:
                update_id = update.get("update_id", 0)
                offset = max(offset, update_id + 1)

                # --- inline-keyboard callback ---
                cb = update.get("callback_query")
                if cb:
                    data = cb.get("data", "")
                    if data == f"{CB_APPROVE}:{slug}":
                        self._answer_callback(cb.get("id"))
                        return ("approved", "", offset)
                    if data == f"{CB_CANCEL}:{slug}":
                        self._answer_callback(cb.get("id"))
                        return ("cancelled", "", offset)
                    if data == f"{CB_REVISE}:{slug}":
                        self._answer_callback(
                            cb.get("id"),
                            text="수정 사항을 텍스트로 보내주세요.",
                        )
                        # Now wait for a plain-text message with feedback.
                        fb, offset = self._wait_for_text(
                            offset, deadline
                        )
                        return ("revise", fb, offset)

                # --- plain-text message (unsolicited feedback) ---
                msg = update.get("message")
                if msg and str(msg.get("chat", {}).get("id")) == str(self.chat_id):
                    text = msg.get("text", "")
                    if text:
                        return ("revise", text, offset)

            time.sleep(self.poll_interval)

        return ("timeout", "", offset)

    def revise_draft(
        self,
        draft: DraftDocument,
        feedback: str,
    ) -> DraftDocument:
        """Call Claude API to revise *draft* based on user *feedback*.

        Returns a new ``DraftDocument`` with the updated body.  Falls back
        to the original draft if the API call fails.
        """
        if not self.anthropic_api_key:
            logger.warning("No ANTHROPIC_API_KEY — returning draft unchanged")
            return draft

        prompt = (
            "당신은 소백노무법인의 콘텐츠 에디터입니다.\n"
            "아래 초안을 사용자 피드백에 맞게 수정하세요.\n"
            "5섹션 구조(데이터 팩트, 해석, 비유, 체크리스트, 다음 단계)를 유지하세요.\n"
            "한국어로 작성하세요.\n\n"
            f"## 초안 제목\n{draft.title}\n\n"
            f"## 초안 본문\n{draft.body}\n\n"
            f"## 피드백\n{feedback}\n\n"
            "수정된 본문만 출력하세요."
        )

        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.sonnet_model,
                    "max_tokens": 2048,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
            resp.raise_for_status()
            body = resp.json()
            content_blocks = body.get("content", [])
            revised_body = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    revised_body += block.get("text", "")
            if revised_body.strip():
                return DraftDocument(
                    persona=draft.persona,
                    slug=draft.slug,
                    title=draft.title,
                    body=revised_body.strip(),
                    evidence=list(draft.evidence),
                    word_count=len(revised_body.split()),
                    quality_checks=list(draft.quality_checks),
                )
        except Exception:
            logger.warning("Claude revision failed", exc_info=True)

        return draft

    def run_approval(
        self,
        draft: DraftDocument,
        run_id: str,
    ) -> ApprovalDecision:
        """Full approval loop: preview → wait → (revise → re-preview)* → decision."""
        revision_count = 0
        offset = 0

        for _ in range(MAX_REVISIONS + 1):
            msg_id = self.send_preview(draft, run_id)
            if msg_id is None:
                return ApprovalDecision(
                    action="error", draft=draft, revision_count=revision_count
                )

            action, feedback, offset = self.wait_for_response(
                draft.slug, offset=offset,
            )

            if action == "approved":
                return ApprovalDecision(
                    action="approved",
                    draft=draft,
                    revision_count=revision_count,
                )
            if action == "cancelled":
                return ApprovalDecision(
                    action="cancelled",
                    draft=draft,
                    revision_count=revision_count,
                    feedback=feedback,
                )
            if action == "timeout":
                return ApprovalDecision(
                    action="timeout",
                    draft=draft,
                    revision_count=revision_count,
                )
            if action == "revise":
                revision_count += 1
                draft = self.revise_draft(draft, feedback)
                # Loop back to send_preview with the revised draft.
                continue

        # Exhausted revision budget.
        return ApprovalDecision(
            action="cancelled",
            draft=draft,
            revision_count=revision_count,
            feedback="max revisions reached",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _answer_callback(self, callback_id: str | None, text: str = "") -> None:
        if not callback_id:
            return
        payload: dict[str, Any] = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text
        self._tg_post("answerCallbackQuery", payload)

    def _wait_for_text(
        self,
        offset: int,
        deadline: float,
    ) -> tuple[str, int]:
        """Wait for a plain-text message from the boss chat."""
        while time.monotonic() < deadline:
            updates = self._tg_post(
                "getUpdates",
                {"offset": offset, "timeout": min(self.poll_interval, 30)},
            )
            if not updates:
                time.sleep(self.poll_interval)
                continue

            for update in updates:
                update_id = update.get("update_id", 0)
                offset = max(offset, update_id + 1)
                msg = update.get("message")
                if msg and str(msg.get("chat", {}).get("id")) == str(self.chat_id):
                    text = msg.get("text", "")
                    if text:
                        return (text, offset)

            time.sleep(self.poll_interval)

        return ("", offset)


def run_approval_flow(
    config: RuntimeConfig,
    drafts: list[DraftDocument],
    run_id: str,
    *,
    dry_run: bool = False,
) -> list[PublishArtifact]:
    """Pipeline-facing entry point for the approval workflow.

    In dry-run mode returns preview artifacts without sending anything.
    """
    if not (config.telegram_bot_token and config.notify_chat_id):
        return [
            PublishArtifact(
                target="telegram_approval",
                mode="approval",
                location="",
                status="missing_config",
            )
        ]

    if dry_run:
        artifacts: list[PublishArtifact] = []
        for draft in drafts:
            artifacts.append(
                PublishArtifact(
                    target="telegram_approval",
                    mode="approval",
                    location="preview",
                    status="skipped_dry_run",
                    metadata={"title": draft.title, "slug": draft.slug},
                )
            )
        return artifacts

    approval = TelegramApproval(config)
    artifacts = []
    for draft in drafts:
        decision = approval.run_approval(draft, run_id)
        artifacts.append(
            PublishArtifact(
                target="telegram_approval",
                mode="approval",
                location=decision.draft.slug,
                status=decision.action,
                metadata={
                    "title": decision.draft.title,
                    "revision_count": decision.revision_count,
                    "feedback": decision.feedback,
                },
            )
        )
    return artifacts
