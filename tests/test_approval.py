"""Tests for Telegram approval workflow."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.insight_engine.approval import (
    CB_APPROVE,
    CB_CANCEL,
    CB_REVISE,
    ApprovalDecision,
    TelegramApproval,
    run_approval_flow,
)
from src.insight_engine.config import RuntimeConfig
from src.insight_engine.models import DraftDocument


def _make_config(tmp_path, token="tok", chat_id="123", anthropic_key=""):
    return RuntimeConfig(
        repo_root=tmp_path,
        data_root=tmp_path / "data",
        published_root=tmp_path / "published",
        reports_root=tmp_path / "reports",
        env_source="test",
        doppler_project="sanjai-ai",
        doppler_config="prd",
        vault_path=None,
        secret_presence={},
        telegram_bot_token=token,
        boss_chat_id=chat_id,
        anthropic_api_key=anthropic_key,
    )


def _make_draft(persona="nomu"):
    return DraftDocument(
        persona=persona,
        slug=f"{persona}_draft",
        title=f"[소백 노무사] 테스트 초안",
        body="## 데이터 팩트\n\n- 산재 15건\n\n## 해석\n\n내용\n\n## 비유\n\n비유\n\n## 체크리스트\n\n1. 확인\n\n## 다음 단계\n\nCTA",
        evidence=["ev1"],
        word_count=20,
        quality_checks=["pass"],
    )


class TestSendPreview:
    """Test 1: send_preview sends message with inline keyboard."""

    def test_send_preview_returns_message_id(self, tmp_path):
        config = _make_config(tmp_path)
        approval = TelegramApproval(config)

        with patch.object(approval, "_tg_post") as mock_post:
            mock_post.return_value = {"message_id": 42}
            msg_id = approval.send_preview(_make_draft(), "run-1")

        assert msg_id == 42
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "sendMessage"
        payload = call_args[0][1]
        assert payload["chat_id"] == "123"
        assert "reply_markup" in payload
        keyboard = payload["reply_markup"]["inline_keyboard"][0]
        callback_datas = [btn["callback_data"] for btn in keyboard]
        assert f"{CB_APPROVE}:nomu_draft" in callback_datas
        assert f"{CB_REVISE}:nomu_draft" in callback_datas
        assert f"{CB_CANCEL}:nomu_draft" in callback_datas

    def test_send_preview_returns_none_on_failure(self, tmp_path):
        config = _make_config(tmp_path)
        approval = TelegramApproval(config)

        with patch.object(approval, "_tg_post", return_value=None):
            msg_id = approval.send_preview(_make_draft(), "run-1")

        assert msg_id is None


class TestWaitForResponse:
    """Test 2: wait_for_response handles approve callback."""

    def test_approve_callback(self, tmp_path):
        config = _make_config(tmp_path)
        approval = TelegramApproval(config, poll_timeout=1)

        updates = [
            {
                "update_id": 100,
                "callback_query": {
                    "id": "cb1",
                    "data": f"{CB_APPROVE}:nomu_draft",
                },
            }
        ]

        with patch.object(approval, "_tg_post") as mock_post:
            # First call returns updates, second is answerCallbackQuery
            mock_post.side_effect = [updates, None]
            action, feedback, offset = approval.wait_for_response(
                "nomu_draft", offset=0,
            )

        assert action == "approved"
        assert feedback == ""
        assert offset == 101

    """Test 3: wait_for_response handles cancel callback."""

    def test_cancel_callback(self, tmp_path):
        config = _make_config(tmp_path)
        approval = TelegramApproval(config, poll_timeout=1)

        updates = [
            {
                "update_id": 200,
                "callback_query": {
                    "id": "cb2",
                    "data": f"{CB_CANCEL}:nomu_draft",
                },
            }
        ]

        with patch.object(approval, "_tg_post") as mock_post:
            mock_post.side_effect = [updates, None]
            action, feedback, offset = approval.wait_for_response(
                "nomu_draft", offset=0,
            )

        assert action == "cancelled"
        assert offset == 201


class TestReviseDraft:
    """Test 4: revise_draft calls Claude API and returns updated draft."""

    def test_revise_draft_with_api(self, tmp_path):
        config = _make_config(tmp_path, anthropic_key="sk-test")
        approval = TelegramApproval(config)
        original = _make_draft()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "## 데이터 팩트\n\n수정된 본문입니다."}]
        }

        with patch("src.insight_engine.approval.httpx.post", return_value=mock_resp) as mock_post:
            revised = approval.revise_draft(original, "더 짧게 써주세요")

        assert revised.body == "## 데이터 팩트\n\n수정된 본문입니다."
        assert revised.slug == original.slug
        assert revised.persona == original.persona
        # Verify Anthropic API was called
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "api.anthropic.com" in call_kwargs[0][0]

    def test_revise_draft_no_api_key(self, tmp_path):
        config = _make_config(tmp_path, anthropic_key="")
        approval = TelegramApproval(config)
        original = _make_draft()

        revised = approval.revise_draft(original, "feedback")
        assert revised is original  # Unchanged


class TestRunApproval:
    """Test 5: run_approval loops through revise then approve."""

    def test_revise_then_approve(self, tmp_path):
        config = _make_config(tmp_path, anthropic_key="sk-test")
        approval = TelegramApproval(config, poll_timeout=1)
        draft = _make_draft()

        call_count = {"send_preview": 0}

        def fake_send_preview(d, run_id):
            call_count["send_preview"] += 1
            return call_count["send_preview"]

        wait_responses = iter([
            ("revise", "비유 부분을 바꿔주세요", 101),
            ("approved", "", 102),
        ])

        with (
            patch.object(approval, "send_preview", side_effect=fake_send_preview),
            patch.object(approval, "wait_for_response", side_effect=lambda slug, offset: next(wait_responses)),
            patch.object(approval, "revise_draft", return_value=_make_draft()),
        ):
            decision = approval.run_approval(draft, "run-1")

        assert decision.action == "approved"
        assert decision.revision_count == 1
        assert call_count["send_preview"] == 2  # Initial + after revision


class TestRunApprovalFlow:
    """Test 6: run_approval_flow pipeline entry point."""

    def test_dry_run_returns_preview_artifacts(self, tmp_path):
        config = _make_config(tmp_path)
        drafts = [_make_draft("nomu"), _make_draft("lawyer")]

        artifacts = run_approval_flow(config, drafts, "run-1", dry_run=True)

        assert len(artifacts) == 2
        assert all(a.status == "skipped_dry_run" for a in artifacts)
        assert all(a.target == "telegram_approval" for a in artifacts)

    def test_missing_config(self, tmp_path):
        config = _make_config(tmp_path, token="", chat_id="")
        artifacts = run_approval_flow(config, [_make_draft()], "run-1")

        assert len(artifacts) == 1
        assert artifacts[0].status == "missing_config"
