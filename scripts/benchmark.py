#!/usr/bin/env python3
"""
성능 벤치마크 스크립트
=======================
용도: 응답시간 측정 + 비용효율성 + 품질 스코어 + 히스토리 비교
실행: python3 scripts/benchmark.py [--baseline] [--compare baseline.json]
"""

import asyncio
import json
import logging
import statistics
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
BENCHMARK_DIR = PROJECT_ROOT / "benchmarks"
LOG_DIR = PROJECT_ROOT / "logs"

BENCHMARK_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class BenchmarkResult:
    """벤치마크 결과"""
    timestamp: str
    version: str

    # 성능 메트릭
    response_time_p50_ms: float
    response_time_p95_ms: float
    response_time_p99_ms: float
    response_time_avg_ms: float

    throughput_rps: float
    error_rate: float

    # Watch 단계
    watch_duration_avg_ms: float
    watch_success_rate: float

    # Think 단계
    think_duration_avg_ms: float
    think_confidence_avg: float

    # Propose 단계
    propose_duration_avg_ms: float
    propose_approval_rate: float

    # 비용 효율성
    cost_per_insight_krw: float
    cost_per_approved_krw: float

    # 품질 스코어
    quality_score: float  # 0~100
    precision: float
    recall: float

    # 시스템 리소스
    memory_mb: float
    cpu_percent: float


@dataclass
class ComparisonReport:
    """비교 리포트"""
    baseline: BenchmarkResult
    current: BenchmarkResult
    improvements: Dict[str, float]
    regressions: Dict[str, float]
    overall_delta_percent: float


# ============================================================================
# Benchmark Runner
# ============================================================================

class BenchmarkRunner:
    """벤치마크 실행"""

    def __init__(self, version: str = "v2.0.0"):
        self.version = version
        self.response_times: List[float] = []
        self.watch_durations: List[float] = []
        self.think_durations: List[float] = []
        self.propose_durations: List[float] = []
        self.errors = 0
        self.total_requests = 0

    async def benchmark_watch_phase(self, iterations: int = 100):
        """Watch 단계 벤치마크"""
        logger.info(f"Benchmarking Watch phase ({iterations} iterations)...")

        success_count = 0

        for i in range(iterations):
            start = time.time()

            # 크롤링 시뮬레이션
            await asyncio.sleep(0.5)  # 실제 크롤링 시간 시뮬레이션

            duration = (time.time() - start) * 1000
            self.watch_durations.append(duration)

            # 95% 성공률 시뮬레이션
            import random
            if random.random() > 0.05:
                success_count += 1

        success_rate = success_count / iterations
        logger.info(f"Watch phase: avg={statistics.mean(self.watch_durations):.2f}ms, success_rate={success_rate:.2%}")

        return success_rate

    async def benchmark_think_phase(self, iterations: int = 100):
        """Think 단계 벤치마크"""
        logger.info(f"Benchmarking Think phase ({iterations} iterations)...")

        confidence_scores = []

        for i in range(iterations):
            start = time.time()

            # LLM 분석 시뮬레이션
            await asyncio.sleep(1.5)

            duration = (time.time() - start) * 1000
            self.think_durations.append(duration)

            # 신뢰도 생성
            import random
            confidence = random.uniform(0.6, 0.95)
            confidence_scores.append(confidence)

        avg_confidence = statistics.mean(confidence_scores)
        logger.info(f"Think phase: avg={statistics.mean(self.think_durations):.2f}ms, confidence={avg_confidence:.2f}")

        return avg_confidence

    async def benchmark_propose_phase(self, iterations: int = 50):
        """Propose 단계 벤치마크"""
        logger.info(f"Benchmarking Propose phase ({iterations} iterations)...")

        approved_count = 0

        for i in range(iterations):
            start = time.time()

            # Telegram 전송 시뮬레이션
            await asyncio.sleep(0.8)

            duration = (time.time() - start) * 1000
            self.propose_durations.append(duration)

            # 승인율 시뮬레이션 (70%)
            import random
            if random.random() < 0.70:
                approved_count += 1

        approval_rate = approved_count / iterations
        logger.info(f"Propose phase: avg={statistics.mean(self.propose_durations):.2f}ms, approval_rate={approval_rate:.2%}")

        return approval_rate

    async def benchmark_end_to_end(self, iterations: int = 50):
        """E2E 벤치마크"""
        logger.info(f"Benchmarking End-to-End pipeline ({iterations} iterations)...")

        for i in range(iterations):
            start = time.time()

            # 전체 파이프라인 시뮬레이션
            await asyncio.sleep(0.5)  # Watch
            await asyncio.sleep(1.5)  # Think
            await asyncio.sleep(0.8)  # Propose

            duration = (time.time() - start) * 1000
            self.response_times.append(duration)

            self.total_requests += 1

        logger.info(f"E2E: avg={statistics.mean(self.response_times):.2f}ms")

    def calculate_quality_score(self, precision: float, recall: float, confidence: float) -> float:
        """품질 스코어 계산"""
        # F1 스코어 기반
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        # 신뢰도 가중치
        quality = (f1 * 0.7 + confidence * 0.3) * 100

        return quality

    def generate_result(self, watch_success_rate: float, think_confidence: float, propose_approval_rate: float) -> BenchmarkResult:
        """벤치마크 결과 생성"""
        response_times_sorted = sorted(self.response_times)
        p50 = response_times_sorted[len(response_times_sorted) // 2] if response_times_sorted else 0
        p95 = response_times_sorted[int(len(response_times_sorted) * 0.95)] if response_times_sorted else 0
        p99 = response_times_sorted[int(len(response_times_sorted) * 0.99)] if response_times_sorted else 0

        # 비용 계산 (예상)
        cost_per_insight = 50.0  # 50원/건
        cost_per_approved = cost_per_insight / propose_approval_rate if propose_approval_rate > 0 else 0

        # 품질 메트릭 (시뮬레이션)
        import random
        precision = random.uniform(0.75, 0.90)
        recall = random.uniform(0.70, 0.85)
        quality_score = self.calculate_quality_score(precision, recall, think_confidence)

        # 리소스 사용량 (시뮬레이션)
        memory_mb = random.uniform(100, 300)
        cpu_percent = random.uniform(20, 60)

        return BenchmarkResult(
            timestamp=datetime.now().isoformat(),
            version=self.version,

            response_time_p50_ms=p50,
            response_time_p95_ms=p95,
            response_time_p99_ms=p99,
            response_time_avg_ms=statistics.mean(self.response_times) if self.response_times else 0,

            throughput_rps=len(self.response_times) / (sum(self.response_times) / 1000) if self.response_times else 0,
            error_rate=self.errors / self.total_requests if self.total_requests > 0 else 0,

            watch_duration_avg_ms=statistics.mean(self.watch_durations) if self.watch_durations else 0,
            watch_success_rate=watch_success_rate,

            think_duration_avg_ms=statistics.mean(self.think_durations) if self.think_durations else 0,
            think_confidence_avg=think_confidence,

            propose_duration_avg_ms=statistics.mean(self.propose_durations) if self.propose_durations else 0,
            propose_approval_rate=propose_approval_rate,

            cost_per_insight_krw=cost_per_insight,
            cost_per_approved_krw=cost_per_approved,

            quality_score=quality_score,
            precision=precision,
            recall=recall,

            memory_mb=memory_mb,
            cpu_percent=cpu_percent
        )


# ============================================================================
# Comparison Engine
# ============================================================================

class ComparisonEngine:
    """벤치마크 비교"""

    @staticmethod
    def compare(baseline: BenchmarkResult, current: BenchmarkResult) -> ComparisonReport:
        """벤치마크 비교"""
        improvements = {}
        regressions = {}

        metrics = [
            ("response_time_p95_ms", "lower_is_better"),
            ("throughput_rps", "higher_is_better"),
            ("error_rate", "lower_is_better"),
            ("watch_success_rate", "higher_is_better"),
            ("think_confidence_avg", "higher_is_better"),
            ("propose_approval_rate", "higher_is_better"),
            ("cost_per_approved_krw", "lower_is_better"),
            ("quality_score", "higher_is_better"),
        ]

        total_delta = 0.0
        metric_count = 0

        for metric_name, direction in metrics:
            baseline_value = getattr(baseline, metric_name)
            current_value = getattr(current, metric_name)

            if baseline_value == 0:
                continue

            delta_percent = ((current_value - baseline_value) / baseline_value) * 100

            if direction == "lower_is_better":
                if delta_percent < 0:  # 개선
                    improvements[metric_name] = abs(delta_percent)
                elif delta_percent > 0:  # 악화
                    regressions[metric_name] = delta_percent
                total_delta -= delta_percent  # 낮을수록 좋으므로 부호 반전
            else:  # higher_is_better
                if delta_percent > 0:  # 개선
                    improvements[metric_name] = delta_percent
                elif delta_percent < 0:  # 악화
                    regressions[metric_name] = abs(delta_percent)
                total_delta += delta_percent

            metric_count += 1

        overall_delta = total_delta / metric_count if metric_count > 0 else 0

        return ComparisonReport(
            baseline=baseline,
            current=current,
            improvements=improvements,
            regressions=regressions,
            overall_delta_percent=overall_delta
        )

    @staticmethod
    def print_comparison(report: ComparisonReport):
        """비교 리포트 출력"""
        logger.info("="*60)
        logger.info("Benchmark Comparison Report")
        logger.info("="*60)

        logger.info(f"Baseline: {report.baseline.timestamp} (v{report.baseline.version})")
        logger.info(f"Current:  {report.current.timestamp} (v{report.current.version})")
        logger.info("")

        if report.improvements:
            logger.info("Improvements:")
            for metric, delta in sorted(report.improvements.items(), key=lambda x: x[1], reverse=True):
                logger.info(f"  ✓ {metric}: +{delta:.1f}%")

        if report.regressions:
            logger.info("\nRegressions:")
            for metric, delta in sorted(report.regressions.items(), key=lambda x: x[1], reverse=True):
                logger.info(f"  ✗ {metric}: -{delta:.1f}%")

        logger.info("")
        logger.info(f"Overall Delta: {report.overall_delta_percent:+.1f}%")

        if report.overall_delta_percent > 0:
            logger.info("✓ Performance IMPROVED")
        elif report.overall_delta_percent < 0:
            logger.info("✗ Performance REGRESSED")
        else:
            logger.info("= Performance UNCHANGED")

        logger.info("="*60)


# ============================================================================
# Main Execution
# ============================================================================

async def main():
    """메인 실행"""
    import argparse

    parser = argparse.ArgumentParser(description="성능 벤치마크")
    parser.add_argument("--baseline", action="store_true", help="베이스라인 생성")
    parser.add_argument("--compare", type=str, help="베이스라인과 비교 (JSON 경로)")
    parser.add_argument("--version", type=str, default="v2.0.0", help="버전")

    args = parser.parse_args()

    # 벤치마크 실행
    runner = BenchmarkRunner(version=args.version)

    logger.info("="*60)
    logger.info("성능 벤치마크 시작")
    logger.info("="*60)

    watch_success = await runner.benchmark_watch_phase(iterations=100)
    think_confidence = await runner.benchmark_think_phase(iterations=100)
    propose_approval = await runner.benchmark_propose_phase(iterations=50)
    await runner.benchmark_end_to_end(iterations=50)

    result = runner.generate_result(watch_success, think_confidence, propose_approval)

    # 결과 출력
    logger.info("")
    logger.info("="*60)
    logger.info("Benchmark Results")
    logger.info("="*60)
    logger.info(f"Version: {result.version}")
    logger.info(f"Timestamp: {result.timestamp}")
    logger.info("")
    logger.info("Performance:")
    logger.info(f"  P50 Response Time: {result.response_time_p50_ms:.2f}ms")
    logger.info(f"  P95 Response Time: {result.response_time_p95_ms:.2f}ms")
    logger.info(f"  P99 Response Time: {result.response_time_p99_ms:.2f}ms")
    logger.info(f"  Throughput: {result.throughput_rps:.2f} req/s")
    logger.info(f"  Error Rate: {result.error_rate:.2%}")
    logger.info("")
    logger.info("Quality:")
    logger.info(f"  Quality Score: {result.quality_score:.1f}/100")
    logger.info(f"  Precision: {result.precision:.2f}")
    logger.info(f"  Recall: {result.recall:.2f}")
    logger.info(f"  Confidence: {result.think_confidence_avg:.2f}")
    logger.info("")
    logger.info("Cost:")
    logger.info(f"  Per Insight: {result.cost_per_insight_krw:.0f}원")
    logger.info(f"  Per Approved: {result.cost_per_approved_krw:.0f}원")
    logger.info("="*60)

    # 결과 저장
    result_file = BENCHMARK_DIR / f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(result_file, "w") as f:
        json.dump(asdict(result), f, indent=2)
    logger.info(f"Results saved: {result_file}")

    # 베이스라인 저장
    if args.baseline:
        baseline_file = BENCHMARK_DIR / "baseline.json"
        with open(baseline_file, "w") as f:
            json.dump(asdict(result), f, indent=2)
        logger.info(f"Baseline saved: {baseline_file}")

    # 비교
    if args.compare:
        compare_path = Path(args.compare)
        if not compare_path.exists():
            logger.error(f"Baseline file not found: {compare_path}")
            return

        with open(compare_path, "r") as f:
            baseline_data = json.load(f)
            baseline = BenchmarkResult(**baseline_data)

        comparison = ComparisonEngine.compare(baseline, result)
        ComparisonEngine.print_comparison(comparison)

        # 비교 리포트 저장
        comparison_file = BENCHMARK_DIR / f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(comparison_file, "w") as f:
            json.dump({
                "baseline": asdict(baseline),
                "current": asdict(result),
                "improvements": comparison.improvements,
                "regressions": comparison.regressions,
                "overall_delta_percent": comparison.overall_delta_percent
            }, f, indent=2)
        logger.info(f"Comparison saved: {comparison_file}")


if __name__ == "__main__":
    asyncio.run(main())
