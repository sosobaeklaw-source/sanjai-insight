"""
Batch Processing System with job scheduling and parallel execution.

Features:
- Distributed job scheduling
- Parallel task execution
- Retry logic with exponential backoff
- Job dependency management
- Progress tracking and monitoring
"""

import asyncio
import logging
import sqlite3
import time
import os
from typing import Dict, List, Optional, Callable, Any, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
import json
import traceback
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import hashlib

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Job execution status."""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class JobPriority(Enum):
    """Job priority levels."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class JobConfig:
    """Job configuration."""
    max_retries: int = 3
    retry_delay: int = 60  # seconds
    timeout: int = 3600  # 1 hour
    priority: JobPriority = JobPriority.NORMAL
    depends_on: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class Job:
    """Batch job definition."""
    job_id: str
    job_type: str
    payload: Dict[str, Any]
    config: JobConfig
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    attempts: int = 0
    error_message: Optional[str] = None
    result: Optional[Dict] = None


@dataclass
class BatchResult:
    """Batch execution result."""
    batch_id: str
    total_jobs: int
    completed: int
    failed: int
    cancelled: int
    elapsed_seconds: float
    results: List[Dict] = field(default_factory=list)


class JobQueue:
    """
    Priority-based job queue with dependency management.

    Features:
    - Priority-based scheduling
    - Job dependencies
    - Persistence to SQLite
    """

    def __init__(self, db_path: str = "data/batch_jobs.db"):
        """Initialize job queue."""
        self.db_path = db_path
        self._ensure_db()
        self._pending_jobs: Dict[str, Job] = {}
        self._load_pending_jobs()

    def _ensure_db(self):
        """Create job database."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    config TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    attempts INTEGER DEFAULT 0,
                    error_message TEXT,
                    result TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status
                ON jobs(status)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_priority_created
                ON jobs(status, created_at)
            """)

    def _load_pending_jobs(self):
        """Load pending jobs from database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT job_id, job_type, payload, config, status, created_at,
                       started_at, completed_at, attempts, error_message, result
                FROM jobs
                WHERE status IN ('pending', 'scheduled', 'retrying')
                ORDER BY created_at
            """)

            for row in cursor.fetchall():
                job = self._row_to_job(row)
                self._pending_jobs[job.job_id] = job

    def _row_to_job(self, row) -> Job:
        """Convert database row to Job object."""
        return Job(
            job_id=row[0],
            job_type=row[1],
            payload=json.loads(row[2]),
            config=JobConfig(**json.loads(row[3])),
            status=JobStatus(row[4]),
            created_at=datetime.fromisoformat(row[5]),
            started_at=datetime.fromisoformat(row[6]) if row[6] else None,
            completed_at=datetime.fromisoformat(row[7]) if row[7] else None,
            attempts=row[8],
            error_message=row[9],
            result=json.loads(row[10]) if row[10] else None
        )

    def enqueue(self, job: Job):
        """
        Add job to queue.

        Args:
            job: Job to enqueue
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO jobs
                (job_id, job_type, payload, config, status, created_at, attempts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                job.job_id,
                job.job_type,
                json.dumps(job.payload),
                json.dumps(asdict(job.config)),
                job.status.value,
                job.created_at.isoformat(),
                job.attempts
            ))

        self._pending_jobs[job.job_id] = job
        logger.info(f"Enqueued job {job.job_id} ({job.job_type})")

    def get_next_job(self) -> Optional[Job]:
        """
        Get next job to execute.

        Returns:
            Next job or None if queue empty
        """
        # Filter jobs ready to run (no dependencies)
        ready_jobs = []

        for job in self._pending_jobs.values():
            if job.status not in [JobStatus.PENDING, JobStatus.SCHEDULED]:
                continue

            # Check dependencies
            dependencies_met = True
            for dep_id in job.config.depends_on:
                if dep_id in self._pending_jobs:
                    dependencies_met = False
                    break

                # Check if dependency completed successfully
                dep_job = self.get_job(dep_id)
                if not dep_job or dep_job.status != JobStatus.COMPLETED:
                    dependencies_met = False
                    break

            if dependencies_met:
                ready_jobs.append(job)

        if not ready_jobs:
            return None

        # Sort by priority then creation time
        ready_jobs.sort(
            key=lambda j: (
                -j.config.priority.value,
                j.created_at
            )
        )

        return ready_jobs[0]

    def update_job(self, job: Job):
        """
        Update job status.

        Args:
            job: Job with updated status
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE jobs
                SET status = ?, started_at = ?, completed_at = ?,
                    attempts = ?, error_message = ?, result = ?
                WHERE job_id = ?
            """, (
                job.status.value,
                job.started_at.isoformat() if job.started_at else None,
                job.completed_at.isoformat() if job.completed_at else None,
                job.attempts,
                job.error_message,
                json.dumps(job.result) if job.result else None,
                job.job_id
            ))

        # Remove from pending if completed/failed/cancelled
        if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            if job.job_id in self._pending_jobs:
                del self._pending_jobs[job.job_id]

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        if job_id in self._pending_jobs:
            return self._pending_jobs[job_id]

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT job_id, job_type, payload, config, status, created_at,
                       started_at, completed_at, attempts, error_message, result
                FROM jobs
                WHERE job_id = ?
            """, (job_id,))

            row = cursor.fetchone()
            if row:
                return self._row_to_job(row)

        return None

    def cancel_job(self, job_id: str):
        """Cancel pending job."""
        job = self.get_job(job_id)
        if job and job.status in [JobStatus.PENDING, JobStatus.SCHEDULED]:
            job.status = JobStatus.CANCELLED
            self.update_job(job)
            logger.info(f"Cancelled job {job_id}")

    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT status, COUNT(*)
                FROM jobs
                GROUP BY status
            """)

            stats = {}
            for row in cursor.fetchall():
                stats[row[0]] = row[1]

            return stats


class BatchProcessor:
    """
    Batch job processor with parallel execution.

    Features:
    - Parallel job execution
    - Automatic retry with exponential backoff
    - Job timeout handling
    - Progress tracking
    """

    def __init__(
        self,
        job_queue: JobQueue,
        max_workers: int = 4,
        use_processes: bool = False
    ):
        """
        Initialize batch processor.

        Args:
            job_queue: Job queue instance
            max_workers: Maximum parallel workers
            use_processes: Use processes instead of threads
        """
        self.job_queue = job_queue
        self.max_workers = max_workers
        self.use_processes = use_processes

        self._job_handlers: Dict[str, Callable] = {}
        self._running = False
        self._executor = None

    def register_handler(self, job_type: str, handler: Callable):
        """
        Register job handler function.

        Args:
            job_type: Job type identifier
            handler: Handler function (job: Job) -> result
        """
        self._job_handlers[job_type] = handler
        logger.info(f"Registered handler for job type: {job_type}")

    async def process_job(self, job: Job) -> bool:
        """
        Process single job.

        Args:
            job: Job to process

        Returns:
            True if successful
        """
        if job.job_type not in self._job_handlers:
            logger.error(f"No handler for job type: {job.job_type}")
            job.status = JobStatus.FAILED
            job.error_message = f"No handler registered for {job.job_type}"
            self.job_queue.update_job(job)
            return False

        handler = self._job_handlers[job.job_type]

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        job.attempts += 1
        self.job_queue.update_job(job)

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                self._execute_handler(handler, job),
                timeout=job.config.timeout
            )

            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.result = result
            self.job_queue.update_job(job)

            logger.info(f"Completed job {job.job_id}")
            return True

        except asyncio.TimeoutError:
            logger.error(f"Job {job.job_id} timed out")
            return await self._handle_job_error(
                job,
                f"Timeout after {job.config.timeout}s"
            )

        except Exception as e:
            logger.error(f"Job {job.job_id} failed: {e}")
            return await self._handle_job_error(job, str(e))

    async def _execute_handler(self, handler: Callable, job: Job) -> Any:
        """Execute job handler in executor."""
        loop = asyncio.get_event_loop()

        if self._executor is None:
            if self.use_processes:
                self._executor = ProcessPoolExecutor(max_workers=self.max_workers)
            else:
                self._executor = ThreadPoolExecutor(max_workers=self.max_workers)

        return await loop.run_in_executor(
            self._executor,
            handler,
            job
        )

    async def _handle_job_error(self, job: Job, error: str) -> bool:
        """
        Handle job error with retry logic.

        Args:
            job: Failed job
            error: Error message

        Returns:
            True if will retry, False if permanent failure
        """
        job.error_message = error

        if job.attempts < job.config.max_retries:
            job.status = JobStatus.RETRYING

            # Exponential backoff
            delay = job.config.retry_delay * (2 ** (job.attempts - 1))

            logger.info(
                f"Retrying job {job.job_id} in {delay}s "
                f"(attempt {job.attempts}/{job.config.max_retries})"
            )

            self.job_queue.update_job(job)

            # Schedule retry
            await asyncio.sleep(delay)
            job.status = JobStatus.PENDING
            self.job_queue.update_job(job)

            return True
        else:
            job.status = JobStatus.FAILED
            job.completed_at = datetime.utcnow()
            self.job_queue.update_job(job)

            logger.error(
                f"Job {job.job_id} failed permanently after "
                f"{job.attempts} attempts"
            )

            return False

    async def start(self):
        """Start processing jobs."""
        self._running = True
        logger.info(f"Started batch processor with {self.max_workers} workers")

        tasks = []

        while self._running:
            # Clean up completed tasks
            tasks = [t for t in tasks if not t.done()]

            # Start new tasks if capacity available
            while len(tasks) < self.max_workers:
                job = self.job_queue.get_next_job()

                if not job:
                    break

                task = asyncio.create_task(self.process_job(job))
                tasks.append(task)

            # Wait briefly before checking for more jobs
            await asyncio.sleep(1)

            # Exit if no jobs and no running tasks
            if not tasks and not self.job_queue.get_next_job():
                break

        # Wait for remaining tasks
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Batch processor stopped")

    def stop(self):
        """Stop processing jobs."""
        self._running = False

        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None


class BatchScheduler:
    """
    Schedule batch jobs with cron-like expressions.

    Features:
    - Recurring job scheduling
    - Cron-like expressions
    - Job templates
    """

    def __init__(self, job_queue: JobQueue):
        """Initialize scheduler."""
        self.job_queue = job_queue
        self._schedules: Dict[str, Dict] = {}

    def schedule_recurring(
        self,
        schedule_id: str,
        job_type: str,
        payload: Dict,
        interval_seconds: int,
        config: Optional[JobConfig] = None
    ):
        """
        Schedule recurring job.

        Args:
            schedule_id: Schedule identifier
            job_type: Job type
            payload: Job payload template
            interval_seconds: Interval between runs
            config: Job configuration
        """
        self._schedules[schedule_id] = {
            "job_type": job_type,
            "payload": payload,
            "interval_seconds": interval_seconds,
            "config": config or JobConfig(),
            "last_run": None
        }

        logger.info(
            f"Scheduled recurring job {schedule_id} "
            f"(every {interval_seconds}s)"
        )

    async def run(self):
        """Run scheduler loop."""
        while True:
            now = datetime.utcnow()

            for schedule_id, schedule in self._schedules.items():
                last_run = schedule["last_run"]
                interval = schedule["interval_seconds"]

                # Check if it's time to run
                if (not last_run or
                    (now - last_run).total_seconds() >= interval):

                    # Create job from template
                    job_id = f"{schedule_id}_{int(time.time())}"

                    job = Job(
                        job_id=job_id,
                        job_type=schedule["job_type"],
                        payload=schedule["payload"].copy(),
                        config=schedule["config"]
                    )

                    self.job_queue.enqueue(job)
                    schedule["last_run"] = now

            await asyncio.sleep(10)  # Check every 10 seconds
