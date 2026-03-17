"""
LLM Tools - Claude/Gemini 호출 래퍼
비용 추적 + 에러 핸들링
"""

import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import anthropic
import google.generativeai as genai

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM 클라이언트 (Claude + Gemini)"""

    # 모델별 가격 (USD / 1M tokens)
    PRICING = {
        "claude-opus-4-6": {"input": 15.0, "output": 75.0},
        "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
        "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
        "gemini-2.0-flash-exp": {"input": 0.0, "output": 0.0},  # Free tier
        "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
    }

    def __init__(self):
        # API 키 로드
        self.anthropic_client = None
        if os.getenv("ANTHROPIC_API_KEY"):
            self.anthropic_client = anthropic.Anthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY")
            )

        if os.getenv("GOOGLE_API_KEY"):
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

    async def call(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        LLM 호출 (통합 인터페이스)

        Returns:
            (response_text, metadata)
            metadata: {
                model: str,
                tokens_in: int,
                tokens_out: int,
                latency_ms: int,
                cost_usd: float
            }
        """
        start_time = time.time()

        # Claude
        if model.startswith("claude"):
            response_text, meta = await self._call_claude(
                model, prompt, system, temperature, max_tokens
            )

        # Gemini
        elif model.startswith("gemini"):
            response_text, meta = await self._call_gemini(
                model, prompt, system, temperature, max_tokens
            )

        else:
            raise ValueError(f"Unknown model: {model}")

        # 비용 계산
        latency_ms = int((time.time() - start_time) * 1000)
        cost_usd = self._calculate_cost(
            model, meta["tokens_in"], meta["tokens_out"]
        )

        meta.update(
            {
                "latency_ms": latency_ms,
                "cost_usd": cost_usd,
            }
        )

        logger.info(
            f"[LLM] {model} | {meta['tokens_in']}→{meta['tokens_out']}tk | "
            f"{latency_ms}ms | ${cost_usd:.4f}"
        )

        return response_text, meta

    async def _call_claude(
        self,
        model: str,
        prompt: str,
        system: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> Tuple[str, Dict[str, Any]]:
        """Claude API 호출"""
        if not self.anthropic_client:
            raise RuntimeError("Anthropic API key not configured")

        messages = [{"role": "user", "content": prompt}]

        response = self.anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or "",
            messages=messages,
        )

        response_text = response.content[0].text

        meta = {
            "model": model,
            "tokens_in": response.usage.input_tokens,
            "tokens_out": response.usage.output_tokens,
        }

        return response_text, meta

    async def _call_gemini(
        self,
        model: str,
        prompt: str,
        system: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> Tuple[str, Dict[str, Any]]:
        """Gemini API 호출"""
        # 모델 초기화
        gemini_model = genai.GenerativeModel(model)

        # System instruction 적용
        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        # 생성
        response = gemini_model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )

        response_text = response.text

        # 토큰 추정 (Gemini는 usage 정보가 제한적)
        tokens_in = self._estimate_tokens(full_prompt)
        tokens_out = self._estimate_tokens(response_text)

        meta = {
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }

        return response_text, meta

    def _estimate_tokens(self, text: str) -> int:
        """토큰 추정 (1 token ≈ 2.5자)"""
        return max(1, int(len(text) / 2.5))

    def _calculate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """비용 계산 (USD)"""
        pricing = None
        for model_key, p in self.PRICING.items():
            if model_key in model:
                pricing = p
                break

        if not pricing:
            # Unknown model → 보수적 추정 (Sonnet 가격)
            pricing = {"input": 3.0, "output": 15.0}

        cost_usd = (
            tokens_in / 1_000_000 * pricing["input"]
            + tokens_out / 1_000_000 * pricing["output"]
        )

        return round(cost_usd, 6)
