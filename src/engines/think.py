"""
Think Engine - 인사이트 생성 (Evidence 기반)
3종 프레임: CASE_IMPACT, MARKET_OPPORTUNITY, STRATEGY_SHIFT
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aiosqlite

from ..models import EventType, InsightType
from ..core.events import EventLogger
from ..core.checkpoint import CheckpointManager
from ..core.termination import TerminationChecker
from ..tools.llm_tools import LLMClient
from .validation import validate_insight_evidence_binding, store_insight_claims

logger = logging.getLogger(__name__)


class ThinkEngine:
    """Think Engine - Evidence 기반 인사이트 생성"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.event_logger = EventLogger(db_path)
        self.llm_client = LLMClient()

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
        Think 실행 (Worker 핸들러)

        Args:
            correlation_id: 실행 추적 ID
            payload: {frames: ["CASE_IMPACT", "MARKET_OPPORTUNITY"]}
            ctx: 체크포인트 컨텍스트
            checker: 종료 조건 체크
            checkpoint_manager: 체크포인트 관리
            event_logger: 이벤트 로거

        Returns:
            {insights_generated: int, insights_passed: int, total_cost_usd: float}
        """
        frames = payload.get(
            "frames", ["CASE_IMPACT", "MARKET_OPPORTUNITY", "STRATEGY_SHIFT"]
        )

        # 시작 이벤트
        try:
            await event_logger.log(
                EventType.THINK_START,
                correlation_id,
                {"frames": frames},
            )
        except Exception as e:
            logger.warning(f"[Think] Event logging failed: {e}")

        # Evidence 로드
        evidence_map = await self._load_evidence(correlation_id)
        logger.info(f"[Think] Loaded {len(evidence_map)} evidence items")

        if not evidence_map:
            logger.warning("[Think] No evidence available - skipping")
            try:
                await event_logger.log(
                    EventType.THINK_END,
                    correlation_id,
                    {"insights_generated": 0, "reason": "no_evidence"},
                )
            except Exception as e:
                logger.warning(f"[Think] Event logging failed: {e}")
            return {
                "insights_generated": 0,
                "insights_passed": 0,
                "total_cost_usd": 0.0,
            }

        insights_generated = 0
        insights_passed = 0
        total_cost_usd = 0.0

        for frame in frames:
            # 종료 조건 체크
            should_terminate, reason = checker.check()
            if should_terminate:
                logger.warning(f"[Think] Termination: {reason}")
                try:
                    await event_logger.log(
                        EventType.TERMINATION,
                        correlation_id,
                        {"reason": reason, "stage": "THINK"},
                    )
                except Exception as e:
                    logger.warning(f"[Think] Event logging failed: {e}")
                break

            try:
                logger.info(f"[Think] Processing frame: {frame}")

                # 프레임별 인사이트 생성
                insight, cost_usd = await self._generate_insight(
                    frame=frame,
                    evidence_map=evidence_map,
                    correlation_id=correlation_id,
                    checker=checker,
                )

                if insight:
                    insights_generated += 1
                    total_cost_usd += cost_usd

                    # Evidence Gate 검증
                    is_valid, errors = await self._validate_insight(
                        insight, evidence_map
                    )

                    if is_valid:
                        # DB 저장
                        await self._save_insight(insight, correlation_id)
                        insights_passed += 1

                        # 성공 이벤트
                        try:
                            await event_logger.log(
                                EventType.INSIGHT_CREATED,
                                correlation_id,
                                {"insight_id": insight["insight_id"], "frame": frame},
                            )
                        except Exception as e:
                            logger.warning(f"[Think] Event logging failed: {e}")
                    else:
                        # 실패 이벤트
                        try:
                            await event_logger.log(
                                EventType.INSIGHT_REJECTED,
                                correlation_id,
                                {
                                    "frame": frame,
                                    "reason": "evidence_gate_failed",
                                    "errors": errors,
                                },
                            )
                        except Exception as e:
                            logger.warning(f"[Think] Event logging failed: {e}")

                # 비용 추적
                checker.add_cost(cost_usd)

                # 체크포인트 저장
                try:
                    ctx["think_progress"] = {
                        "completed_frames": frame,
                        "insights_generated": insights_generated,
                        "insights_passed": insights_passed,
                        "total_cost_usd": total_cost_usd,
                    }
                    await checkpoint_manager.save(correlation_id, "THINK", ctx)
                except Exception as e:
                    logger.warning(f"[Think] Checkpoint save failed: {e}")

            except Exception as e:
                logger.error(f"[Think] Error processing frame {frame}: {e}")
                try:
                    await event_logger.log(
                        EventType.ERROR,
                        correlation_id,
                        {"error": str(e), "frame": frame, "stage": "THINK"},
                    )
                except Exception as log_error:
                    logger.warning(f"[Think] Event logging failed: {log_error}")
                continue

        # 완료 이벤트
        try:
            await event_logger.log(
                EventType.THINK_END,
                correlation_id,
                {
                    "insights_generated": insights_generated,
                    "insights_passed": insights_passed,
                    "total_cost_usd": total_cost_usd,
                },
            )
        except Exception as e:
            logger.warning(f"[Think] Event logging failed: {e}")

        return {
            "insights_generated": insights_generated,
            "insights_passed": insights_passed,
            "total_cost_usd": total_cost_usd,
        }

    async def _load_evidence(self, correlation_id: str) -> Dict[str, Dict[str, Any]]:
        """Evidence 로드 (correlation_id 기준)"""
        evidence_map = {}

        try:
            async with aiosqlite.connect(self.db_path, timeout=10.0) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    """
                    SELECT * FROM evidence
                    WHERE correlation_id = ?
                    ORDER BY created_at DESC
                    LIMIT 100
                    """,
                    (correlation_id,),
                )
                rows = await cursor.fetchall()

                for row in rows:
                    try:
                        evidence_map[row["evidence_id"]] = {
                            "evidence_id": row["evidence_id"],
                            "source_type": row["source_type"],
                            "locator_json": json.loads(row["locator_json"]),
                            "snippet": row["snippet"],
                            "content_hash": row["content_hash"],
                        }
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.error(f"[Think] Failed to parse evidence row: {e}")
                        continue
        except TimeoutError:
            logger.error("[Think] Database timeout loading evidence")
        except Exception as e:
            logger.error(f"[Think] Failed to load evidence: {e}")

        return evidence_map

    async def _generate_insight(
        self,
        frame: str,
        evidence_map: Dict[str, Dict],
        correlation_id: str,
        checker: TerminationChecker,
    ) -> tuple[Optional[Dict], float]:
        """
        프레임별 인사이트 생성 (LLM)

        Returns:
            (insight_dict, cost_usd)
        """
        # Evidence 요약 생성
        try:
            evidence_summary = self._summarize_evidence(evidence_map)
        except Exception as e:
            logger.error(f"[Think] Failed to summarize evidence: {e}")
            return None, 0.0

        # 프롬프트 생성
        try:
            system_prompt, user_prompt = self._build_prompts(frame, evidence_summary)
        except Exception as e:
            logger.error(f"[Think] Failed to build prompts: {e}")
            return None, 0.0

        # LLM 호출
        try:
            response_text, meta = await self.llm_client.call(
                model="claude-sonnet-4-5-20250929",
                prompt=user_prompt,
                system=system_prompt,
                temperature=1.0,
                max_tokens=4096,
            )

            # LLM calls 저장
            try:
                await self._save_llm_call(
                    correlation_id=correlation_id,
                    stage="THINK",
                    model=meta["model"],
                    tokens_in=meta["tokens_in"],
                    tokens_out=meta["tokens_out"],
                    latency_ms=meta["latency_ms"],
                    cost_usd=meta["cost_usd"],
                )
            except Exception as e:
                logger.warning(f"[Think] Failed to save LLM call log: {e}")

            # 파싱
            insight = self._parse_insight_response(response_text, frame)

            return insight, meta["cost_usd"]

        except TimeoutError:
            logger.error(f"[Think] LLM call timeout")
            return None, 0.0
        except KeyError as e:
            logger.error(f"[Think] LLM response missing field: {e}")
            return None, 0.0
        except Exception as e:
            logger.error(f"[Think] LLM call failed: {e}")
            return None, 0.0

    def _summarize_evidence(self, evidence_map: Dict[str, Dict]) -> str:
        """Evidence 요약 (프롬프트용)"""
        lines = ["수집된 증거:"]
        for eid, ev in list(evidence_map.items())[:20]:  # 최대 20개
            lines.append(f"- [{eid}] {ev['snippet'][:100]}...")
        return "\n".join(lines)

    def _build_prompts(
        self, frame: str, evidence_summary: str
    ) -> tuple[str, str]:
        """프롬프트 생성"""
        system_prompt = f"""당신은 산재 전문 노무사의 인사이트 분석 AI입니다.

주어진 증거를 기반으로 {frame} 프레임의 인사이트를 생성하세요.

**중요 규칙:**
1. 모든 주장(claim)은 반드시 증거 ID([E123] 형식)를 명시해야 합니다
2. 증거 없는 추측/가정은 금지합니다
3. 출력은 JSON 형식으로만 작성하세요

**출력 형식:**
{{
  "title": "인사이트 제목",
  "confidence": 0.85,
  "urgency": "HIGH",
  "claims": [
    {{"text": "주장 내용", "evidence_ids": ["E1", "E2"]}},
    ...
  ],
  "suggested_actions": ["액션1", "액션2"]
}}"""

        user_prompt = f"""프레임: {frame}

{evidence_summary}

위 증거를 기반으로 인사이트를 생성하세요."""

        return system_prompt, user_prompt

    def _parse_insight_response(
        self, response_text: str, frame: str
    ) -> Optional[Dict]:
        """LLM 응답 파싱"""
        try:
            # JSON 추출 (```json ... ``` 제거)
            if "```json" in response_text:
                start = response_text.index("```json") + 7
                end = response_text.rindex("```")
                response_text = response_text[start:end].strip()

            insight_data = json.loads(response_text)

            # 필수 필드 검증
            required = ["title", "confidence", "urgency", "claims"]
            for field in required:
                if field not in insight_data:
                    logger.error(f"[Think] Missing field: {field}")
                    return None

            # insight 객체 구성
            insight = {
                "insight_id": str(uuid4()),
                "type": frame,
                "title": insight_data["title"],
                "confidence": insight_data["confidence"],
                "urgency": insight_data["urgency"],
                "claims": insight_data["claims"],
                "suggested_actions": insight_data.get("suggested_actions", []),
                "body": insight_data,  # 전체 저장
            }

            return insight

        except Exception as e:
            logger.error(f"[Think] Failed to parse insight: {e}")
            return None

    async def _validate_insight(
        self, insight: Dict, evidence_map: Dict
    ) -> tuple[bool, List[str]]:
        """Evidence Gate 검증"""
        claims = insight.get("claims", [])

        is_valid, errors = await validate_insight_evidence_binding(
            db_path=self.db_path,
            insight_id=insight["insight_id"],
            claims=claims,
            evidence_map=evidence_map,
        )

        return is_valid, errors

    async def _save_insight(self, insight: Dict, correlation_id: str):
        """Insight + Claims 저장"""
        try:
            async with aiosqlite.connect(self.db_path, timeout=10.0) as db:
                # insight 저장
                await db.execute(
                    """
                    INSERT INTO insights
                    (id, type, trigger_data_ids, title, body, confidence, urgency,
                     suggested_actions, affected_cases, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        insight["insight_id"],
                        insight["type"],
                        "[]",  # trigger_data_ids (legacy)
                        insight["title"],
                        json.dumps(insight["body"], ensure_ascii=False),
                        insight["confidence"],
                        insight["urgency"],
                        json.dumps(insight["suggested_actions"], ensure_ascii=False),
                        "[]",  # affected_cases
                        "NEW",
                    ),
                )

                await db.commit()

            # claims 저장
            await store_insight_claims(
                self.db_path, insight["insight_id"], insight["claims"]
            )
        except TimeoutError:
            logger.error(f"[Think] Database timeout saving insight {insight['insight_id']}")
            raise
        except Exception as e:
            logger.error(f"[Think] Failed to save insight: {e}")
            raise

    async def _save_llm_call(
        self,
        correlation_id: str,
        stage: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: int,
        cost_usd: float,
    ):
        """LLM 호출 로그 저장"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO llm_calls
                (id, correlation_id, stage, model, tokens_in, tokens_out, latency_ms, cost_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    correlation_id,
                    stage,
                    model,
                    tokens_in,
                    tokens_out,
                    latency_ms,
                    cost_usd,
                ),
            )
            await db.commit()
