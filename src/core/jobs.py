"""
Job Manager for Idempotent Scheduling
Prevents duplicate job execution with job_key uniqueness
"""

import json
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

import aiosqlite

from ..models import Job, JobStatus


class JobManager:
    """Manages scheduled jobs with idempotency"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def enqueue(
        self,
        job_key: str,
        job_type: str,
        payload: dict[str, Any],
        max_attempts: int = 3,
    ) -> Optional[str]:
        """
        Enqueue job (idempotent via job_key)
        Returns: job_id if created, None if already exists
        """
        job_id = str(uuid4())

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO jobs (job_id, job_key, type, payload_json, status, max_attempts)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        job_key,
                        job_type,
                        json.dumps(payload, ensure_ascii=False),
                        JobStatus.PENDING.value,
                        max_attempts,
                    ),
                )
                await db.commit()
                return job_id
        except aiosqlite.IntegrityError:
            # job_key already exists (idempotent)
            return None

    async def poll(self, limit: int = 1) -> list[Job]:
        """
        Poll pending jobs (FIFO)
        Returns: list of jobs (up to limit)
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                """
                SELECT * FROM jobs
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (JobStatus.PENDING.value, limit),
            )

            rows = await cursor.fetchall()
            return [self._row_to_job(row) for row in rows]

    async def mark_running(self, job_id: str) -> None:
        """Mark job as running"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE jobs
                SET status = ?, started_at = ?, attempts = attempts + 1
                WHERE job_id = ?
                """,
                (JobStatus.RUNNING.value, datetime.now().isoformat(), job_id),
            )
            await db.commit()

    async def mark_completed(self, job_id: str) -> None:
        """Mark job as completed"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE jobs
                SET status = ?, completed_at = ?
                WHERE job_id = ?
                """,
                (JobStatus.COMPLETED.value, datetime.now().isoformat(), job_id),
            )
            await db.commit()

    async def mark_failed(self, job_id: str, error: str, retry: bool = True) -> None:
        """
        Mark job as failed
        If retry=True and attempts < max_attempts, requeue as PENDING
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Get current job
            cursor = await db.execute(
                "SELECT attempts, max_attempts FROM jobs WHERE job_id = ?",
                (job_id,),
            )
            row = await cursor.fetchone()

            if not row:
                return

            attempts = row["attempts"]
            max_attempts = row["max_attempts"]

            # Check if should retry
            if retry and attempts < max_attempts:
                # Requeue as PENDING
                await db.execute(
                    """
                    UPDATE jobs
                    SET status = ?, last_error = ?
                    WHERE job_id = ?
                    """,
                    (JobStatus.PENDING.value, error, job_id),
                )
            else:
                # Mark as FAILED (no more retries)
                await db.execute(
                    """
                    UPDATE jobs
                    SET status = ?, last_error = ?, completed_at = ?
                    WHERE job_id = ?
                    """,
                    (JobStatus.FAILED.value, error, datetime.now().isoformat(), job_id),
                )

            await db.commit()

    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                "SELECT * FROM jobs WHERE job_id = ?",
                (job_id,),
            )
            row = await cursor.fetchone()

            return self._row_to_job(row) if row else None

    async def get_job_by_key(self, job_key: str) -> Optional[Job]:
        """Get job by job_key"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                "SELECT * FROM jobs WHERE job_key = ?",
                (job_key,),
            )
            row = await cursor.fetchone()

            return self._row_to_job(row) if row else None

    def _row_to_job(self, row: aiosqlite.Row) -> Job:
        """Convert DB row to Job model"""
        return Job(
            job_id=row["job_id"],
            job_key=row["job_key"],
            type=row["type"],
            payload_json=json.loads(row["payload_json"]),
            status=JobStatus(row["status"]),
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            last_error=row["last_error"],
        )
