"""
Termination Checker for Resource Limits
Prevents runaway costs and infinite loops
"""

from datetime import datetime
from typing import Optional

from ..models import TerminationCondition


class TerminationChecker:
    """Checks termination conditions during execution"""

    def __init__(self, condition: TerminationCondition):
        self.condition = condition
        self.start_time: Optional[datetime] = None
        self.total_cost_usd: float = 0.0
        self.retry_count: int = 0
        self.rebuild_count: int = 0

    def start(self) -> None:
        """Mark execution start"""
        self.start_time = datetime.now()

    def add_cost(self, cost_usd: float) -> None:
        """Add cost to total"""
        self.total_cost_usd += cost_usd

    def increment_retry(self) -> None:
        """Increment retry count"""
        self.retry_count += 1

    def increment_rebuild(self) -> None:
        """Increment rebuild count"""
        self.rebuild_count += 1

    def check(self) -> tuple[bool, str]:
        """
        Check if termination conditions are met
        Returns: (should_terminate, reason)
        """
        # Cost check
        if self.total_cost_usd >= self.condition.max_cost_usd:
            return (
                True,
                f"Cost limit exceeded: ${self.total_cost_usd:.2f} >= ${self.condition.max_cost_usd:.2f}",
            )

        # Time check
        if self.start_time:
            elapsed_sec = (datetime.now() - self.start_time).total_seconds()
            if elapsed_sec >= self.condition.max_time_sec:
                return (
                    True,
                    f"Time limit exceeded: {elapsed_sec:.0f}s >= {self.condition.max_time_sec}s",
                )

        # Retry check
        if self.retry_count >= self.condition.max_retries:
            return (
                True,
                f"Retry limit exceeded: {self.retry_count} >= {self.condition.max_retries}",
            )

        # Rebuild check
        if self.rebuild_count >= self.condition.max_rebuilds:
            return (
                True,
                f"Rebuild limit exceeded: {self.rebuild_count} >= {self.condition.max_rebuilds}",
            )

        return (False, "")

    def get_status(self) -> dict[str, any]:
        """Get current termination status"""
        elapsed_sec = 0
        if self.start_time:
            elapsed_sec = (datetime.now() - self.start_time).total_seconds()

        return {
            "elapsed_sec": elapsed_sec,
            "total_cost_usd": self.total_cost_usd,
            "retry_count": self.retry_count,
            "rebuild_count": self.rebuild_count,
            "limits": {
                "max_cost_usd": self.condition.max_cost_usd,
                "max_time_sec": self.condition.max_time_sec,
                "max_retries": self.condition.max_retries,
                "max_rebuilds": self.condition.max_rebuilds,
            },
        }
