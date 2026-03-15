#!/usr/bin/env python3
"""
부하 테스트 프레임워크 (Locust 기반)
=======================================
용도: 50건 인사이트 생성 시뮬레이션 + 성능 메트릭 수집
실행: locust -f tests/load_test.py --host=http://localhost:8000
"""

import json
import logging
import random
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

try:
    from locust import HttpUser, task, between, events
    from locust.runners import MasterRunner, WorkerRunner
except ImportError:
    if "pytest" in sys.modules:
        import pytest

        pytest.skip("locust not installed", allow_module_level=True)
    raise

# ============================================================================
# Configuration
# ============================================================================

# 부하 테스트 설정
INSIGHT_TARGET = 50  # 목표 인사이트 생성 수
CONFIDENCE_THRESHOLD = 0.7
SIMULATE_APPROVAL = True  # 승인 시뮬레이션 여부

# 성능 임계값 (SLA)
RESPONSE_TIME_P95 = 5000  # 95th percentile < 5초
RESPONSE_TIME_P99 = 10000  # 99th percentile < 10초
ERROR_RATE_MAX = 0.01  # 에러율 < 1%
THROUGHPUT_MIN = 1.0  # 최소 처리량 (req/sec)

# 크롤링 시뮬레이션 데이터
SAMPLE_URLS = [
    "https://www.moel.go.kr/news/notice/{}.do".format(i) for i in range(1000, 1100)
]

SAMPLE_KEYWORDS = [
    "산재보험", "업무상재해", "요양급여", "휴업급여", "장해급여",
    "유족급여", "산재신청", "산재인정", "업무상질병", "직업병",
    "산재예방", "안전보건", "근로복지", "장해등급", "재요양"
]

SAMPLE_COMPETITORS = [
    "법무법인 A", "법무법인 B", "노무법인 C",
    "노무법인 D", "법무법인 E"
]

# ============================================================================
# Performance Tracking
# ============================================================================

class PerformanceMetrics:
    """성능 메트릭 수집"""

    def __init__(self):
        self.insights_generated = 0
        self.insights_approved = 0
        self.insights_rejected = 0
        self.total_latency = []
        self.errors = []
        self.bottlenecks = {}
        self.start_time = time.time()

    def record_insight(self, latency: float, approved: bool):
        """인사이트 생성 기록"""
        self.insights_generated += 1
        self.total_latency.append(latency)
        if approved:
            self.insights_approved += 1
        else:
            self.insights_rejected += 1

    def record_error(self, error_type: str, message: str):
        """에러 기록"""
        self.errors.append({
            "type": error_type,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })

    def record_bottleneck(self, stage: str, duration: float):
        """병목 지점 기록"""
        if stage not in self.bottlenecks:
            self.bottlenecks[stage] = []
        self.bottlenecks[stage].append(duration)

    def get_summary(self) -> Dict[str, Any]:
        """성능 요약"""
        elapsed = time.time() - self.start_time

        latency_sorted = sorted(self.total_latency)
        p50 = latency_sorted[len(latency_sorted) // 2] if latency_sorted else 0
        p95 = latency_sorted[int(len(latency_sorted) * 0.95)] if latency_sorted else 0
        p99 = latency_sorted[int(len(latency_sorted) * 0.99)] if latency_sorted else 0

        bottleneck_summary = {}
        for stage, durations in self.bottlenecks.items():
            bottleneck_summary[stage] = {
                "mean": sum(durations) / len(durations),
                "max": max(durations),
                "min": min(durations)
            }

        return {
            "duration_seconds": elapsed,
            "insights_generated": self.insights_generated,
            "insights_approved": self.insights_approved,
            "insights_rejected": self.insights_rejected,
            "throughput_per_sec": self.insights_generated / elapsed if elapsed > 0 else 0,
            "latency": {
                "p50_ms": p50 * 1000,
                "p95_ms": p95 * 1000,
                "p99_ms": p99 * 1000,
                "mean_ms": (sum(self.total_latency) / len(self.total_latency) * 1000) if self.total_latency else 0
            },
            "errors": {
                "count": len(self.errors),
                "rate": len(self.errors) / self.insights_generated if self.insights_generated > 0 else 0,
                "details": self.errors[:10]  # 최근 10개만
            },
            "bottlenecks": bottleneck_summary,
            "sla_compliance": {
                "p95_under_5s": p95 * 1000 < RESPONSE_TIME_P95,
                "p99_under_10s": p99 * 1000 < RESPONSE_TIME_P99,
                "error_rate_under_1pct": (len(self.errors) / self.insights_generated if self.insights_generated > 0 else 0) < ERROR_RATE_MAX,
                "throughput_over_1rps": (self.insights_generated / elapsed if elapsed > 0 else 0) >= THROUGHPUT_MIN
            }
        }


# Global metrics instance
metrics = PerformanceMetrics()


# ============================================================================
# Locust User Classes
# ============================================================================

class InsightGenerationUser(HttpUser):
    """인사이트 생성 시뮬레이션"""

    wait_time = between(1, 5)  # 1~5초 대기 (자연스러운 부하)

    def on_start(self):
        """사용자 초기화"""
        self.user_id = f"load_test_user_{random.randint(1000, 9999)}"
        logging.info(f"User {self.user_id} started")

    @task(3)
    def health_check(self):
        """Health check (가벼운 작업, 높은 빈도)"""
        with self.client.get("/healthz", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")

    @task(2)
    def get_status(self):
        """Status check"""
        with self.client.get("/status", catch_response=True) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "status" in data:
                        response.success()
                    else:
                        response.failure("Invalid status response")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"Status check failed: {response.status_code}")

    @task(1)
    def get_metrics(self):
        """Metrics check"""
        with self.client.get("/metrics", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Metrics check failed: {response.status_code}")

    @task(5)
    def simulate_watch_phase(self):
        """Watch 단계 시뮬레이션 (크롤링)"""
        start_time = time.time()

        # 랜덤 URL 크롤링 시뮬레이션
        url = random.choice(SAMPLE_URLS)
        keyword = random.choice(SAMPLE_KEYWORDS)

        # Note: 실제 크롤링 엔드포인트가 없으므로 시뮬레이션만
        # 실제 구현 시 POST /api/crawl 등의 엔드포인트 호출

        duration = time.time() - start_time
        metrics.record_bottleneck("watch", duration)

        # 크롤링 결과 시뮬레이션
        if random.random() > 0.05:  # 95% 성공률
            logging.debug(f"Watch phase completed: {keyword} from {url}")
        else:
            metrics.record_error("CrawlError", f"Failed to crawl {url}")

    @task(4)
    def simulate_think_phase(self):
        """Think 단계 시뮬레이션 (분석)"""
        start_time = time.time()

        # LLM 분석 시뮬레이션 (실제로는 시간이 더 오래 걸림)
        time.sleep(random.uniform(1.0, 3.0))

        duration = time.time() - start_time
        metrics.record_bottleneck("think", duration)

        # 분석 결과 시뮬레이션
        confidence = random.uniform(0.5, 0.95)
        if confidence >= CONFIDENCE_THRESHOLD:
            logging.debug(f"Think phase: High confidence insight ({confidence:.2f})")
        else:
            logging.debug(f"Think phase: Low confidence, filtered ({confidence:.2f})")

    @task(2)
    def simulate_propose_phase(self):
        """Propose 단계 시뮬레이션 (제안)"""
        start_time = time.time()

        # 제안 생성 시뮬레이션
        confidence = random.uniform(CONFIDENCE_THRESHOLD, 0.95)

        # Telegram 메시지 전송 시뮬레이션 (실제 전송 없음)
        time.sleep(random.uniform(0.5, 1.5))

        duration = time.time() - start_time
        metrics.record_bottleneck("propose", duration)

        # 승인/거절 시뮬레이션
        if SIMULATE_APPROVAL:
            approved = random.random() > 0.3  # 70% 승인율
            metrics.record_insight(duration, approved)
            logging.info(f"Insight proposed and {'approved' if approved else 'rejected'} (confidence: {confidence:.2f})")

    @task(1)
    def simulate_full_pipeline(self):
        """전체 파이프라인 시뮬레이션 (Watch → Think → Propose)"""
        start_time = time.time()

        # Watch
        watch_start = time.time()
        time.sleep(random.uniform(0.5, 1.5))
        metrics.record_bottleneck("watch", time.time() - watch_start)

        # Think
        think_start = time.time()
        time.sleep(random.uniform(1.0, 3.0))
        confidence = random.uniform(0.5, 0.95)
        metrics.record_bottleneck("think", time.time() - think_start)

        if confidence < CONFIDENCE_THRESHOLD:
            logging.debug("Pipeline: Insight filtered (low confidence)")
            return

        # Propose
        propose_start = time.time()
        time.sleep(random.uniform(0.5, 1.5))
        metrics.record_bottleneck("propose", time.time() - propose_start)

        total_duration = time.time() - start_time
        approved = random.random() > 0.3
        metrics.record_insight(total_duration, approved)

        logging.info(f"Full pipeline completed in {total_duration:.2f}s, {'approved' if approved else 'rejected'}")


# ============================================================================
# Event Handlers
# ============================================================================

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """테스트 시작 시"""
    logging.info("="*60)
    logging.info("부하 테스트 시작")
    logging.info(f"목표: {INSIGHT_TARGET}건 인사이트 생성")
    logging.info("="*60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """테스트 종료 시"""
    summary = metrics.get_summary()

    logging.info("="*60)
    logging.info("부하 테스트 완료")
    logging.info("="*60)
    logging.info(json.dumps(summary, indent=2))

    # SLA 체크
    sla_pass = all(summary["sla_compliance"].values())
    if sla_pass:
        logging.info("✓ SLA 준수")
    else:
        logging.warning("✗ SLA 위반:")
        for key, value in summary["sla_compliance"].items():
            if not value:
                logging.warning(f"  - {key}")

    # 병목 지점 식별
    if summary["bottlenecks"]:
        logging.info("\n병목 지점:")
        for stage, stats in summary["bottlenecks"].items():
            logging.info(f"  {stage}: mean={stats['mean']:.2f}s, max={stats['max']:.2f}s")

    # 성능 리포트 저장
    report_path = f"logs/load_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        import os
        os.makedirs("logs", exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(summary, f, indent=2)
        logging.info(f"\n성능 리포트 저장: {report_path}")
    except Exception as e:
        logging.error(f"Failed to save report: {e}")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """각 요청마다 호출"""
    if exception:
        metrics.record_error("RequestError", str(exception))


# ============================================================================
# CLI Entry Point
# ============================================================================

if __name__ == "__main__":
    import sys

    print("""
부하 테스트 프레임워크
======================
사용법:
  locust -f tests/load_test.py --host=http://localhost:8000

옵션:
  --users 10           동시 사용자 수
  --spawn-rate 1       초당 사용자 생성 수
  --run-time 10m       실행 시간
  --headless           웹 UI 없이 실행

예제:
  # 웹 UI로 실행
  locust -f tests/load_test.py --host=http://localhost:8000

  # 헤드리스 모드 (10명 사용자, 5분)
  locust -f tests/load_test.py --host=http://localhost:8000 \\
    --users 10 --spawn-rate 1 --run-time 5m --headless

  # 분산 부하 테스트
  locust -f tests/load_test.py --master --expect-workers 4
    """)
