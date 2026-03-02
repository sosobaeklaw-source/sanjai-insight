"""
Worker for Job Execution
Polls jobs and executes with checkpoint/termination support
"""

import asyncio
import traceback
from datetime import datetime
from typing import Any, Callable, Dict
from uuid import uuid4

import aiosqlite

from ..models import EventType, RunStatus, TerminationCondition
from .checkpoint import CheckpointManager
from .events import EventLogger
from .jobs import JobManager
from .termination import TerminationChecker


class Worker:
    """Background worker for job execution"""

    def __init__(
        self,
        db_path: str,
        handlers: Dict[str, Callable],
        termination_condition: TerminationCondition,
    ):
        """
        Initialize worker
        Args:
            db_path: Database path
            handlers: Dict[job_type, async_handler_func]
            termination_condition: Termination limits
        """
        self.db_path = db_path
        self.handlers = handlers
        self.termination_condition = termination_condition

        self.job_manager = JobManager(db_path)
        self.checkpoint_manager = CheckpointManager(db_path)
        self.event_logger = EventLogger(db_path)

        self.running = False

    async def start(self, poll_interval: int = 5) -> None:
        """Start worker loop"""
        self.running = True

        while self.running:
            try:
                # Poll for pending jobs
                jobs = await self.job_manager.poll(limit=1)

                if not jobs:
                    await asyncio.sleep(poll_interval)
                    continue

                job = jobs[0]

                # Execute job
                await self.execute_job(job.job_id)

            except Exception as e:
                print(f"Worker error: {e}")
                traceback.print_exc()
                await asyncio.sleep(poll_interval)

    async def stop(self) -> None:
        """Stop worker"""
        self.running = False

    async def execute_job(self, job_id: str) -> None:
        """
        Execute a single job with checkpoint/termination support
        """
        job = await self.job_manager.get_job(job_id)
        if not job:
            return

        # Mark as running
        await self.job_manager.mark_running(job_id)

        # Create run_id
        run_id = str(uuid4())
        correlation_id = job.job_key  # Use job_key as correlation_id

        # Create runlog
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO runlogs (run_id, correlation_id, job_id, status, started_at, meta_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    correlation_id,
                    job_id,
                    RunStatus.RUNNING.value,
                    datetime.now().isoformat(),
                    "{}",
                ),
            )
            await db.commit()

        # Initialize termination checker
        checker = TerminationChecker(self.termination_condition)
        checker.start()

        # Check for existing checkpoint
        checkpoint = await self.checkpoint_manager.load(correlation_id)
        ctx = checkpoint.ctx_json if checkpoint else {}

        try:
            # Get handler
            handler = self.handlers.get(job.type)
            if not handler:
                raise ValueError(f"No handler for job type: {job.type}")

            # Log start event
            await self.event_logger.log(
                EventType.WATCH_START,
                correlation_id,
                {"job_id": job_id, "job_type": job.type},
            )

            # Execute handler
            result = await handler(
                correlation_id=correlation_id,
                payload=job.payload_json,
                ctx=ctx,
                checker=checker,
                checkpoint_manager=self.checkpoint_manager,
                event_logger=self.event_logger,
            )

            # Check termination
            should_terminate, reason = checker.check()
            if should_terminate:
                # Log termination
                await self.event_logger.log(
                    EventType.TERMINATION,
                    correlation_id,
                    {"reason": reason, "status": checker.get_status()},
                )

                # Update runlog
                await self._update_runlog(
                    run_id,
                    RunStatus.TERMINATED,
                    checker.total_cost_usd,
                    {"termination_reason": reason},
                )

                # Mark job as failed
                await self.job_manager.mark_failed(job_id, reason, retry=False)

                return

            # Success
            await self.event_logger.log(
                EventType.WATCH_END,
                correlation_id,
                {"job_id": job_id, "result": result},
            )

            # Update runlog
            await self._update_runlog(
                run_id,
                RunStatus.COMPLETED,
                checker.total_cost_usd,
                {"result": result},
            )

            # Mark job as completed
            await self.job_manager.mark_completed(job_id)

            # Delete checkpoint
            await self.checkpoint_manager.delete(correlation_id)

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            error_trace = traceback.format_exc()

            # Log error event
            await self.event_logger.log(
                EventType.ERROR,
                correlation_id,
                {"error": error_msg, "trace": error_trace},
            )

            # Update runlog
            await self._update_runlog(
                run_id,
                RunStatus.FAILED,
                checker.total_cost_usd,
                {"error": error_msg},
            )

            # Mark job as failed (with retry)
            await self.job_manager.mark_failed(job_id, error_msg, retry=True)

    async def _update_runlog(
        self,
        run_id: str,
        status: RunStatus,
        total_cost_usd: float,
        meta: Dict[str, Any],
    ) -> None:
        """Update runlog with final status"""
        async with aiosqlite.connect(self.db_path) as db:
            import json

            await db.execute(
                """
                UPDATE runlogs
                SET status = ?, ended_at = ?, total_cost_usd = ?, meta_json = ?
                WHERE run_id = ?
                """,
                (
                    status.value,
                    datetime.now().isoformat(),
                    total_cost_usd,
                    json.dumps(meta, ensure_ascii=False),
                    run_id,
                ),
            )
            await db.commit()
