"""
sanjai-insight Application Entry Point
Worker + Handlers 통합
"""

import asyncio
import logging
import os
from typing import Any, Dict

from .core.worker import Worker
from .core.jobs import JobManager
from .engines.watch import WatchEngine
from .engines.think import ThinkEngine
from .engines.propose import ProposeEngine
from .engines.self_diagnose import SelfDiagnoseEngine
from .models import TerminationCondition

logger = logging.getLogger(__name__)


# Handler 함수들
async def watch_handler(
    correlation_id: str,
    payload: Dict[str, Any],
    ctx: Dict[str, Any],
    checker,
    checkpoint_manager,
    event_logger,
) -> Dict[str, Any]:
    """Watch 핸들러"""
    db_path = os.getenv("DB_PATH", "data/insight.db")
    engine = WatchEngine(db_path)
    return await engine.run(
        correlation_id, payload, ctx, checker, checkpoint_manager, event_logger
    )


async def think_handler(
    correlation_id: str,
    payload: Dict[str, Any],
    ctx: Dict[str, Any],
    checker,
    checkpoint_manager,
    event_logger,
) -> Dict[str, Any]:
    """Think 핸들러"""
    db_path = os.getenv("DB_PATH", "data/insight.db")
    engine = ThinkEngine(db_path)
    return await engine.run(
        correlation_id, payload, ctx, checker, checkpoint_manager, event_logger
    )


async def propose_handler(
    correlation_id: str,
    payload: Dict[str, Any],
    ctx: Dict[str, Any],
    checker,
    checkpoint_manager,
    event_logger,
) -> Dict[str, Any]:
    """Propose 핸들러"""
    db_path = os.getenv("DB_PATH", "data/insight.db")
    engine = ProposeEngine(db_path)
    return await engine.run(
        correlation_id, payload, ctx, checker, checkpoint_manager, event_logger
    )


async def diagnose_handler(
    correlation_id: str,
    payload: Dict[str, Any],
    ctx: Dict[str, Any],
    checker,
    checkpoint_manager,
    event_logger,
) -> Dict[str, Any]:
    """Self-Diagnose 핸들러"""
    db_path = os.getenv("DB_PATH", "data/insight.db")
    engine = SelfDiagnoseEngine(db_path)
    return await engine.run(
        correlation_id, payload, ctx, checker, checkpoint_manager, event_logger
    )


async def main():
    """Application main"""
    logging.basicConfig(level=logging.INFO)

    db_path = os.getenv("DB_PATH", "data/insight.db")

    # 핸들러 등록
    handlers = {
        "WATCH": watch_handler,
        "THINK": think_handler,
        "PROPOSE": propose_handler,
        "DIAGNOSE": diagnose_handler,
    }

    # Termination 조건
    termination_condition = TerminationCondition(
        max_cost_usd=float(os.getenv("MAX_COST_USD", "5.0")),
        max_time_sec=int(os.getenv("MAX_TIME_SEC", "3600")),
        max_retries=int(os.getenv("MAX_RETRIES", "3")),
        max_rebuilds=int(os.getenv("MAX_REBUILDS", "3")),
    )

    # Worker 생성
    worker = Worker(
        db_path=db_path,
        handlers=handlers,
        termination_condition=termination_condition,
    )

    # Worker 시작
    logger.info("[App] Starting worker...")
    await worker.start(poll_interval=5)


if __name__ == "__main__":
    asyncio.run(main())
