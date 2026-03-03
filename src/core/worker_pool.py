"""
Dynamic Worker Pool
Adjusts worker count based on load (CPU, memory, queue depth).
"""

import logging
import os
import psutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class WorkerPoolMetrics:
    """Worker pool metrics"""
    active_workers: int
    total_workers: int
    queue_size: int
    cpu_percent: float
    memory_percent: float
    completed_tasks: int
    failed_tasks: int


class DynamicWorkerPool:
    """Worker pool with dynamic scaling based on load"""

    def __init__(
        self,
        min_workers: int = 2,
        max_workers: int = 10,
        initial_workers: int = 4,
        cpu_threshold: float = 80.0,
        memory_threshold: float = 90.0,
        scale_up_queue_size: int = 10,
        scale_down_idle_time: int = 300  # 5 minutes
    ):
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.scale_up_queue_size = scale_up_queue_size
        self.scale_down_idle_time = scale_down_idle_time

        self._current_workers = initial_workers
        self._executor = ThreadPoolExecutor(max_workers=initial_workers)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._scaler_thread: Optional[threading.Thread] = None

        self._completed_tasks = 0
        self._failed_tasks = 0
        self._last_activity_time = time.time()

        # Get from environment if available
        env_workers = os.getenv("WORKER_POOL_SIZE")
        if env_workers:
            try:
                self._current_workers = int(env_workers)
                self._executor = ThreadPoolExecutor(max_workers=self._current_workers)
                logger.info("Worker pool initialized from env: %d workers", self._current_workers)
            except ValueError:
                pass

        logger.info(
            "Worker pool initialized: %d workers (min=%d, max=%d)",
            self._current_workers, self.min_workers, self.max_workers
        )

    def start_autoscaler(self):
        """Start automatic scaling thread"""
        if self._scaler_thread and self._scaler_thread.is_alive():
            logger.warning("Autoscaler already running")
            return

        self._stop_event.clear()
        self._scaler_thread = threading.Thread(
            target=self._autoscaler_loop,
            daemon=True,
            name="WorkerPoolAutoscaler"
        )
        self._scaler_thread.start()
        logger.info("Worker pool autoscaler started")

    def stop_autoscaler(self):
        """Stop automatic scaling thread"""
        if not self._scaler_thread or not self._scaler_thread.is_alive():
            return

        logger.info("Stopping worker pool autoscaler...")
        self._stop_event.set()
        self._scaler_thread.join(timeout=10)

        if self._scaler_thread.is_alive():
            logger.warning("Autoscaler thread did not stop gracefully")

    def _autoscaler_loop(self):
        """Main autoscaler loop"""
        while not self._stop_event.is_set():
            try:
                self._check_and_scale()
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error("Error in autoscaler loop: %s", e, exc_info=True)
                time.sleep(60)  # Wait longer on error

    def _check_and_scale(self):
        """Check metrics and scale if needed"""
        # Get system metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_percent = psutil.virtual_memory().percent

        # Get queue size (estimate from executor)
        queue_size = len(self._executor._threads) if hasattr(self._executor, "_threads") else 0

        # Scale up conditions
        should_scale_up = (
            cpu_percent > self.cpu_threshold or
            memory_percent > self.memory_threshold or
            queue_size > self.scale_up_queue_size
        )

        if should_scale_up and self._current_workers < self.max_workers:
            self._scale_up()

        # Scale down conditions
        idle_time = time.time() - self._last_activity_time
        should_scale_down = (
            cpu_percent < 30 and
            memory_percent < 50 and
            queue_size == 0 and
            idle_time > self.scale_down_idle_time
        )

        if should_scale_down and self._current_workers > self.min_workers:
            self._scale_down()

    def _scale_up(self):
        """Scale up worker count"""
        with self._lock:
            new_count = min(self._current_workers + 1, self.max_workers)

            if new_count == self._current_workers:
                return

            logger.info("Scaling up workers: %d -> %d", self._current_workers, new_count)

            # Create new executor with more workers
            old_executor = self._executor
            self._executor = ThreadPoolExecutor(max_workers=new_count)
            self._current_workers = new_count

            # Shutdown old executor gracefully
            old_executor.shutdown(wait=False)

    def _scale_down(self):
        """Scale down worker count"""
        with self._lock:
            new_count = max(self._current_workers - 1, self.min_workers)

            if new_count == self._current_workers:
                return

            logger.info("Scaling down workers: %d -> %d", self._current_workers, new_count)

            # Create new executor with fewer workers
            old_executor = self._executor
            self._executor = ThreadPoolExecutor(max_workers=new_count)
            self._current_workers = new_count

            # Shutdown old executor gracefully
            old_executor.shutdown(wait=False)

    def submit(self, fn: Callable, *args, **kwargs):
        """Submit task to worker pool"""
        self._last_activity_time = time.time()
        return self._executor.submit(fn, *args, **kwargs)

    def map(self, fn: Callable, *iterables, timeout: Optional[float] = None):
        """Map function over iterables using worker pool"""
        self._last_activity_time = time.time()
        return self._executor.map(fn, *iterables, timeout=timeout)

    def shutdown(self, wait: bool = True):
        """Shutdown worker pool"""
        logger.info("Shutting down worker pool...")
        self.stop_autoscaler()
        self._executor.shutdown(wait=wait)
        logger.info("Worker pool shut down")

    def get_metrics(self) -> WorkerPoolMetrics:
        """Get current worker pool metrics"""
        return WorkerPoolMetrics(
            active_workers=len([t for t in threading.enumerate() if "ThreadPoolExecutor" in t.name]),
            total_workers=self._current_workers,
            queue_size=0,  # Approximate
            cpu_percent=psutil.cpu_percent(interval=0.1),
            memory_percent=psutil.virtual_memory().percent,
            completed_tasks=self._completed_tasks,
            failed_tasks=self._failed_tasks
        )

    def execute_with_retry(
        self,
        fn: Callable,
        *args,
        max_retries: int = 3,
        timeout: Optional[float] = None,
        **kwargs
    ):
        """
        Execute function with retry logic.

        Args:
            fn: Function to execute
            max_retries: Maximum number of retries
            timeout: Timeout in seconds
            *args, **kwargs: Arguments to pass to fn

        Returns:
            Result of fn(*args, **kwargs)

        Raises:
            Exception if all retries fail
        """
        last_exception = None

        for attempt in range(max_retries):
            try:
                future = self.submit(fn, *args, **kwargs)
                result = future.result(timeout=timeout)
                self._completed_tasks += 1
                return result

            except TimeoutError:
                last_exception = TimeoutError(f"Task timed out after {timeout}s")
                logger.warning(
                    "Task timeout (attempt %d/%d): %s",
                    attempt + 1, max_retries, fn.__name__
                )

            except Exception as e:
                last_exception = e
                logger.warning(
                    "Task failed (attempt %d/%d): %s - %s",
                    attempt + 1, max_retries, fn.__name__, e
                )

                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff

        # All retries failed
        self._failed_tasks += 1
        logger.error(
            "Task failed after %d attempts: %s",
            max_retries, fn.__name__
        )
        raise last_exception


# Global worker pool instance
_worker_pool: Optional[DynamicWorkerPool] = None


def get_worker_pool() -> DynamicWorkerPool:
    """Get global worker pool instance"""
    global _worker_pool

    if _worker_pool is None:
        min_workers = int(os.getenv("WORKER_POOL_MIN", "2"))
        max_workers = int(os.getenv("WORKER_POOL_MAX", "10"))
        initial_workers = int(os.getenv("WORKER_POOL_SIZE", "4"))

        _worker_pool = DynamicWorkerPool(
            min_workers=min_workers,
            max_workers=max_workers,
            initial_workers=initial_workers
        )

        # Start autoscaler if enabled
        if os.getenv("WORKER_POOL_AUTOSCALE", "true").lower() == "true":
            _worker_pool.start_autoscaler()

    return _worker_pool


def shutdown_worker_pool():
    """Shutdown global worker pool"""
    global _worker_pool

    if _worker_pool:
        _worker_pool.shutdown()
        _worker_pool = None
