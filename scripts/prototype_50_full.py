#!/usr/bin/env python3
"""
프로토타입 50건 완전 자동화 스크립트
====================================
용도: 50건 실제 케이스 시뮬레이션 + 품질 메트릭 + Threshold 최적화
실행: python3 scripts/prototype_50_full.py [--dry-run] [--report pdf]
"""

import asyncio
import json
import logging
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
import statistics

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import yaml
    from pydantic import BaseModel
except ImportError:
    print("Required packages not installed. Run: pip install pyyaml pydantic")
    sys.exit(1)

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"
LOG_DIR = PROJECT_ROOT / "logs"
REPORT_DIR = PROJECT_ROOT / "reports"

DB_PATH = DATA_DIR / "insight.db"
THRESHOLDS_PATH = CONFIG_DIR / "thresholds.yaml"

# 프로토타입 목표
TARGET_INSIGHTS = 50
CONFIDENCE_INITIAL = 0.7
DAILY_LIMIT = 3

# 시뮬레이션 설정
SIMULATE_CRAWLING = True
SIMULATE_LLM = True
SIMULATE_APPROVAL = True
APPROVAL_RATE = 0.7  # 70% 승인율
DRY_RUN = False

# ============================================================================
# Logging Setup
# ============================================================================

LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"prototype_50_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class CrawlResult:
    """크롤링 결과"""
    url: str
    content_hash: str
    title: str
    content: str
    source: str
    keywords: List[str]
    crawled_at: datetime
    success: bool = True


@dataclass
class InsightResult:
    """인사이트 생성 결과"""
    crawl_id: str
    title: str
    summary: str
    category: str
    confidence: float
    evidence: Dict[str, Any]
    reasoning: str
    created_at: datetime
    filtered: bool = False
    approved: Optional[bool] = None


@dataclass
class QualityMetrics:
    """품질 메트릭"""
    total_crawled: int
    total_insights_generated: int
    total_insights_proposed: int
    total_approved: int
    total_rejected: int

    confidence_scores: List[float]
    evidence_quality_scores: List[float]

    avg_confidence: float
    min_confidence: float
    max_confidence: float

    false_positive_rate: float  # 승인됐지만 실제로는 낮은 품질
    false_negative_rate: float  # 거절됐지만 실제로는 높은 품질

    watch_duration_avg: float
    think_duration_avg: float
    propose_duration_avg: float

    cost_total_krw: float
    cost_per_insight_krw: float


@dataclass
class ThresholdRecommendation:
    """임계값 최적화 추천"""
    current_threshold: float
    recommended_threshold: float
    reason: str
    expected_improvement: Dict[str, Any]


# ============================================================================
# Database Manager
# ============================================================================

class DatabaseManager:
    """데이터베이스 관리"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    async def connect(self):
        """DB 연결"""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        logger.info(f"Connected to database: {self.db_path}")

    async def close(self):
        """DB 닫기"""
        if self.conn:
            self.conn.close()

    async def insert_crawl_result(self, crawl: CrawlResult) -> str:
        """크롤링 결과 저장"""
        if DRY_RUN:
            return f"dry_run_crawl_{int(time.time())}"

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO crawl_results
            (url, content_hash, title, content, source, keywords, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            crawl.url,
            crawl.content_hash,
            crawl.title,
            crawl.content,
            crawl.source,
            json.dumps(crawl.keywords),
            crawl.crawled_at.isoformat()
        ))
        self.conn.commit()
        return str(cursor.lastrowid)

    async def insert_insight(self, insight: InsightResult) -> str:
        """인사이트 저장"""
        if DRY_RUN:
            return f"dry_run_insight_{int(time.time())}"

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO insights
            (crawl_id, title, summary, category, confidence, evidence, reasoning, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            insight.crawl_id,
            insight.title,
            insight.summary,
            insight.category,
            insight.confidence,
            json.dumps(insight.evidence),
            insight.reasoning,
            insight.created_at.isoformat()
        ))
        self.conn.commit()
        return str(cursor.lastrowid)

    async def update_approval_status(self, insight_id: str, approved: bool):
        """승인 상태 업데이트"""
        if DRY_RUN:
            return

        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE insights SET approved = ?, approved_at = ?
            WHERE id = ?
        """, (approved, datetime.now().isoformat(), insight_id))
        self.conn.commit()


# ============================================================================
# Simulator Classes
# ============================================================================

class CrawlerSimulator:
    """크롤러 시뮬레이터"""

    def __init__(self):
        self.sources = ["moel.go.kr", "moel.go.kr/policy", "law.go.kr", "competitor.com"]
        self.keywords = [
            "산재보험", "업무상재해", "요양급여", "휴업급여", "장해급여",
            "유족급여", "산재신청", "산재인정", "업무상질병", "직업병"
        ]

    async def crawl(self, url: str) -> CrawlResult:
        """크롤링 시뮬레이션"""
        await asyncio.sleep(0.5)  # 크롤링 지연 시뮬레이션

        import hashlib
        import random

        content = f"Sample content from {url} - " + " ".join(random.choices(self.keywords, k=5))
        content_hash = hashlib.md5(content.encode()).hexdigest()

        return CrawlResult(
            url=url,
            content_hash=content_hash,
            title=f"Sample Title - {random.choice(self.keywords)}",
            content=content * 10,  # 긴 콘텐츠 시뮬레이션
            source=random.choice(self.sources),
            keywords=random.sample(self.keywords, 3),
            crawled_at=datetime.now(),
            success=random.random() > 0.05  # 95% 성공률
        )


class ThinkEngineSimulator:
    """Think 엔진 시뮬레이터"""

    async def analyze(self, crawl: CrawlResult) -> Optional[InsightResult]:
        """분석 시뮬레이션"""
        await asyncio.sleep(1.5)  # LLM 지연 시뮬레이션

        import random

        # 랜덤 신뢰도 생성
        confidence = random.uniform(0.5, 0.95)

        # Evidence 품질 점수
        evidence_quality = random.uniform(0.6, 1.0)

        insight = InsightResult(
            crawl_id=crawl.content_hash,
            title=f"Insight: {crawl.title}",
            summary=f"분석 결과: {crawl.keywords[0]}에 대한 새로운 동향",
            category=random.choice(["policy", "trend", "precedent", "competitor"]),
            confidence=confidence,
            evidence={
                "source_url": crawl.url,
                "keywords": crawl.keywords,
                "quality_score": evidence_quality,
                "evidence_count": random.randint(2, 5)
            },
            reasoning=f"키워드 '{crawl.keywords[0]}'에 대한 분석 결과",
            created_at=datetime.now()
        )

        return insight


class ApprovalSimulator:
    """승인 시뮬레이터"""

    def __init__(self, approval_rate: float = 0.7):
        self.approval_rate = approval_rate

    async def simulate_approval(self, insight: InsightResult) -> bool:
        """승인 시뮬레이션"""
        await asyncio.sleep(0.5)  # 승인 대기 시뮬레이션

        import random

        # 높은 신뢰도는 더 높은 승인율
        confidence_factor = (insight.confidence - 0.5) / 0.5  # 0.5~1.0 → 0~1
        adjusted_rate = self.approval_rate + (1 - self.approval_rate) * confidence_factor * 0.3

        return random.random() < adjusted_rate


# ============================================================================
# Prototype Runner
# ============================================================================

class PrototypeRunner:
    """프로토타입 실행 관리자"""

    def __init__(self):
        self.db = DatabaseManager(DB_PATH)
        self.crawler = CrawlerSimulator()
        self.think_engine = ThinkEngineSimulator()
        self.approval_sim = ApprovalSimulator(APPROVAL_RATE)

        self.crawl_results: List[CrawlResult] = []
        self.insights: List[InsightResult] = []

        self.watch_durations: List[float] = []
        self.think_durations: List[float] = []
        self.propose_durations: List[float] = []

        self.total_cost_krw = 0.0

    async def setup(self):
        """초기화"""
        await self.db.connect()
        logger.info("Prototype runner initialized")

    async def teardown(self):
        """정리"""
        await self.db.close()
        logger.info("Prototype runner teardown complete")

    async def run_watch_phase(self, urls: List[str]):
        """Watch 단계 실행"""
        logger.info(f"=== Watch Phase: {len(urls)} URLs ===")

        for url in urls:
            start_time = time.time()
            crawl = await self.crawler.crawl(url)
            duration = time.time() - start_time

            self.watch_durations.append(duration)

            if crawl.success:
                crawl_id = await self.db.insert_crawl_result(crawl)
                self.crawl_results.append(crawl)
                logger.debug(f"✓ Crawled: {url} (#{crawl_id})")
            else:
                logger.warning(f"✗ Failed: {url}")

        logger.info(f"Watch phase complete: {len(self.crawl_results)} successful")

    async def run_think_phase(self):
        """Think 단계 실행"""
        logger.info(f"=== Think Phase: {len(self.crawl_results)} items ===")

        for crawl in self.crawl_results:
            start_time = time.time()
            insight = await self.think_engine.analyze(crawl)
            duration = time.time() - start_time

            self.think_durations.append(duration)

            if insight:
                # 신뢰도 필터링
                if insight.confidence >= CONFIDENCE_INITIAL:
                    insight_id = await self.db.insert_insight(insight)
                    self.insights.append(insight)
                    logger.debug(f"✓ Insight: {insight.title} (conf: {insight.confidence:.2f})")
                else:
                    insight.filtered = True
                    logger.debug(f"✗ Filtered: {insight.title} (conf: {insight.confidence:.2f})")

                # 비용 계산 (Gemini Flash 기준)
                self.total_cost_krw += 0.5  # 예상 비용

        logger.info(f"Think phase complete: {len(self.insights)} insights passed threshold")

    async def run_propose_phase(self):
        """Propose 단계 실행"""
        logger.info(f"=== Propose Phase: {len(self.insights)} proposals ===")

        for insight in self.insights:
            start_time = time.time()

            # 승인 시뮬레이션
            approved = await self.approval_sim.simulate_approval(insight)
            insight.approved = approved

            duration = time.time() - start_time
            self.propose_durations.append(duration)

            # DB 업데이트
            await self.db.update_approval_status(insight.crawl_id, approved)

            status = "✓ Approved" if approved else "✗ Rejected"
            logger.debug(f"{status}: {insight.title}")

        approved_count = sum(1 for i in self.insights if i.approved)
        logger.info(f"Propose phase complete: {approved_count}/{len(self.insights)} approved")

    async def run_full_pipeline(self, iterations: int = 50):
        """전체 파이프라인 실행"""
        logger.info("="*60)
        logger.info(f"프로토타입 50건 시작 (목표: {TARGET_INSIGHTS}건)")
        logger.info("="*60)

        # URL 생성 (시뮬레이션)
        urls = [f"https://example.com/article/{i}" for i in range(1, iterations + 1)]

        # Watch
        await self.run_watch_phase(urls)

        # Think
        await self.run_think_phase()

        # Propose
        await self.run_propose_phase()

        logger.info("="*60)
        logger.info("프로토타입 완료")
        logger.info("="*60)

    def calculate_metrics(self) -> QualityMetrics:
        """품질 메트릭 계산"""
        approved_count = sum(1 for i in self.insights if i.approved)
        rejected_count = sum(1 for i in self.insights if i.approved is False)

        confidence_scores = [i.confidence for i in self.insights]
        evidence_scores = [i.evidence.get("quality_score", 0.8) for i in self.insights]

        # False positive/negative 추정 (시뮬레이션)
        # 실제로는 수동 검토 필요
        import random
        false_positive_rate = random.uniform(0.05, 0.15)
        false_negative_rate = random.uniform(0.10, 0.20)

        return QualityMetrics(
            total_crawled=len(self.crawl_results),
            total_insights_generated=len(self.insights) + sum(1 for i in self.insights if hasattr(i, 'filtered') and i.filtered),
            total_insights_proposed=len(self.insights),
            total_approved=approved_count,
            total_rejected=rejected_count,

            confidence_scores=confidence_scores,
            evidence_quality_scores=evidence_scores,

            avg_confidence=statistics.mean(confidence_scores) if confidence_scores else 0,
            min_confidence=min(confidence_scores) if confidence_scores else 0,
            max_confidence=max(confidence_scores) if confidence_scores else 0,

            false_positive_rate=false_positive_rate,
            false_negative_rate=false_negative_rate,

            watch_duration_avg=statistics.mean(self.watch_durations) if self.watch_durations else 0,
            think_duration_avg=statistics.mean(self.think_durations) if self.think_durations else 0,
            propose_duration_avg=statistics.mean(self.propose_durations) if self.propose_durations else 0,

            cost_total_krw=self.total_cost_krw,
            cost_per_insight_krw=self.total_cost_krw / approved_count if approved_count > 0 else 0
        )

    def optimize_thresholds(self, metrics: QualityMetrics) -> List[ThresholdRecommendation]:
        """임계값 최적화 추천"""
        recommendations = []

        # 신뢰도 임계값 최적화
        current_threshold = CONFIDENCE_INITIAL

        # 승인율이 너무 낮으면 임계값 낮춤
        approval_rate = metrics.total_approved / metrics.total_insights_proposed if metrics.total_insights_proposed > 0 else 0

        if approval_rate < 0.5:
            recommended = max(0.65, current_threshold - 0.05)
            recommendations.append(ThresholdRecommendation(
                current_threshold=current_threshold,
                recommended_threshold=recommended,
                reason="승인율이 낮음 (50% 미만)",
                expected_improvement={
                    "approval_rate": "+10~15%",
                    "false_negative_reduction": "예상 20%"
                }
            ))
        elif approval_rate > 0.85:
            recommended = min(0.80, current_threshold + 0.05)
            recommendations.append(ThresholdRecommendation(
                current_threshold=current_threshold,
                recommended_threshold=recommended,
                reason="승인율이 높음 (85% 이상), 품질 향상 여지",
                expected_improvement={
                    "precision": "+5~10%",
                    "false_positive_reduction": "예상 15%"
                }
            ))

        # False positive가 높으면 임계값 높임
        if metrics.false_positive_rate > 0.10:
            recommended = min(0.80, current_threshold + 0.05)
            recommendations.append(ThresholdRecommendation(
                current_threshold=current_threshold,
                recommended_threshold=recommended,
                reason=f"False positive 비율 높음 ({metrics.false_positive_rate*100:.1f}%)",
                expected_improvement={
                    "precision": "+10~15%",
                    "wasted_proposals": "-20%"
                }
            ))

        return recommendations


# ============================================================================
# Report Generator
# ============================================================================

class ReportGenerator:
    """리포트 생성기"""

    def __init__(self, runner: PrototypeRunner, metrics: QualityMetrics, recommendations: List[ThresholdRecommendation]):
        self.runner = runner
        self.metrics = metrics
        self.recommendations = recommendations

    def generate_text_report(self) -> str:
        """텍스트 리포트"""
        report = []
        report.append("="*60)
        report.append("프로토타입 50건 자동화 리포트")
        report.append("="*60)
        report.append(f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        report.append("[ 실행 결과 ]")
        report.append(f"크롤링: {self.metrics.total_crawled}건")
        report.append(f"인사이트 생성: {self.metrics.total_insights_generated}건")
        report.append(f"임계값 통과: {self.metrics.total_insights_proposed}건")
        report.append(f"승인: {self.metrics.total_approved}건")
        report.append(f"거절: {self.metrics.total_rejected}건")
        report.append(f"승인율: {self.metrics.total_approved / self.metrics.total_insights_proposed * 100:.1f}%" if self.metrics.total_insights_proposed > 0 else "승인율: N/A")
        report.append("")

        report.append("[ 품질 메트릭 ]")
        report.append(f"평균 신뢰도: {self.metrics.avg_confidence:.2f}")
        report.append(f"신뢰도 범위: {self.metrics.min_confidence:.2f} ~ {self.metrics.max_confidence:.2f}")
        report.append(f"False Positive Rate: {self.metrics.false_positive_rate*100:.1f}%")
        report.append(f"False Negative Rate: {self.metrics.false_negative_rate*100:.1f}%")
        report.append("")

        report.append("[ 성능 메트릭 ]")
        report.append(f"Watch 평균: {self.metrics.watch_duration_avg:.2f}초")
        report.append(f"Think 평균: {self.metrics.think_duration_avg:.2f}초")
        report.append(f"Propose 평균: {self.metrics.propose_duration_avg:.2f}초")
        report.append(f"총 처리 시간: {sum([self.metrics.watch_duration_avg, self.metrics.think_duration_avg, self.metrics.propose_duration_avg]):.2f}초/건")
        report.append("")

        report.append("[ 비용 분석 ]")
        report.append(f"총 비용: {self.metrics.cost_total_krw:.0f}원")
        report.append(f"승인 건당 비용: {self.metrics.cost_per_insight_krw:.0f}원")
        report.append("")

        report.append("[ 임계값 최적화 추천 ]")
        if self.recommendations:
            for i, rec in enumerate(self.recommendations, 1):
                report.append(f"\n추천 {i}:")
                report.append(f"  현재: {rec.current_threshold:.2f} → 추천: {rec.recommended_threshold:.2f}")
                report.append(f"  이유: {rec.reason}")
                report.append(f"  기대효과:")
                for key, value in rec.expected_improvement.items():
                    report.append(f"    - {key}: {value}")
        else:
            report.append("  현재 임계값 유지 권장")

        report.append("")
        report.append("="*60)

        return "\n".join(report)

    def save_html_report(self, output_path: Path):
        """HTML 리포트 저장"""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>프로토타입 50건 리포트</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        h2 {{ color: #666; border-bottom: 2px solid #ddd; padding-bottom: 10px; }}
        .metric {{ background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }}
        .recommendation {{ background: #fff3cd; padding: 15px; margin: 10px 0; border-left: 4px solid #ffc107; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #4CAF50; color: white; }}
    </style>
</head>
<body>
    <h1>프로토타입 50건 자동화 리포트</h1>
    <p>생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

    <h2>실행 결과</h2>
    <div class="metric">
        <table>
            <tr><th>항목</th><th>값</th></tr>
            <tr><td>크롤링</td><td>{self.metrics.total_crawled}건</td></tr>
            <tr><td>인사이트 생성</td><td>{self.metrics.total_insights_generated}건</td></tr>
            <tr><td>임계값 통과</td><td>{self.metrics.total_insights_proposed}건</td></tr>
            <tr><td>승인</td><td>{self.metrics.total_approved}건</td></tr>
            <tr><td>거절</td><td>{self.metrics.total_rejected}건</td></tr>
            <tr><td>승인율</td><td>{self.metrics.total_approved / self.metrics.total_insights_proposed * 100:.1f}%</td></tr>
        </table>
    </div>

    <h2>품질 메트릭</h2>
    <div class="metric">
        <p><strong>평균 신뢰도:</strong> {self.metrics.avg_confidence:.2f}</p>
        <p><strong>신뢰도 범위:</strong> {self.metrics.min_confidence:.2f} ~ {self.metrics.max_confidence:.2f}</p>
        <p><strong>False Positive Rate:</strong> {self.metrics.false_positive_rate*100:.1f}%</p>
        <p><strong>False Negative Rate:</strong> {self.metrics.false_negative_rate*100:.1f}%</p>
    </div>

    <h2>임계값 최적화 추천</h2>
    {''.join([f'''
    <div class="recommendation">
        <h3>추천 {i}</h3>
        <p><strong>현재:</strong> {rec.current_threshold:.2f} → <strong>추천:</strong> {rec.recommended_threshold:.2f}</p>
        <p><strong>이유:</strong> {rec.reason}</p>
        <p><strong>기대효과:</strong></p>
        <ul>
            {''.join([f'<li>{k}: {v}</li>' for k, v in rec.expected_improvement.items()])}
        </ul>
    </div>
    ''' for i, rec in enumerate(self.recommendations, 1)]) if self.recommendations else '<p>현재 임계값 유지 권장</p>'}
</body>
</html>
        """

        output_path.parent.mkdir(exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        logger.info(f"HTML report saved: {output_path}")


# ============================================================================
# Main Execution
# ============================================================================

async def main():
    """메인 실행"""
    import argparse

    parser = argparse.ArgumentParser(description="프로토타입 50건 자동화")
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 없이 실행")
    parser.add_argument("--report", choices=["text", "html", "pdf"], default="text", help="리포트 형식")
    parser.add_argument("--iterations", type=int, default=50, help="실행 반복 횟수")

    args = parser.parse_args()

    global DRY_RUN
    DRY_RUN = args.dry_run

    if DRY_RUN:
        logger.info("DRY RUN MODE - No database writes")

    # 프로토타입 실행
    runner = PrototypeRunner()
    await runner.setup()

    try:
        await runner.run_full_pipeline(iterations=args.iterations)

        # 메트릭 계산
        metrics = runner.calculate_metrics()

        # 임계값 최적화
        recommendations = runner.optimize_thresholds(metrics)

        # 리포트 생성
        report_gen = ReportGenerator(runner, metrics, recommendations)

        # 텍스트 리포트
        text_report = report_gen.generate_text_report()
        print("\n" + text_report)

        # 파일 저장
        REPORT_DIR.mkdir(exist_ok=True)
        report_file = REPORT_DIR / f"prototype_50_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        report_file.write_text(text_report, encoding="utf-8")
        logger.info(f"Text report saved: {report_file}")

        # HTML 리포트
        if args.report in ["html", "pdf"]:
            html_file = REPORT_DIR / f"prototype_50_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            report_gen.save_html_report(html_file)

        # JSON 메트릭
        json_file = REPORT_DIR / f"prototype_50_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        json_file.write_text(json.dumps(asdict(metrics), indent=2, default=str), encoding="utf-8")
        logger.info(f"JSON metrics saved: {json_file}")

    finally:
        await runner.teardown()


if __name__ == "__main__":
    asyncio.run(main())
