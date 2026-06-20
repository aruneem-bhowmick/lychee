"""Health checks and runtime metrics for the Lychee service.

Provides ``HealthChecker`` for aggregated health status (server, state store,
workers) and ``MetricsCollector`` for runtime metrics (uptime, queue depth,
active workers, job counters).  Both are designed for use behind HTTP
endpoints: ``GET /health`` returns the aggregate status with 200/503, and
``GET /metrics`` returns a JSON snapshot of current metrics.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from lychee.queue import ReviewQueue, WorkerPool
from lychee.state_store import StateStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class HealthStatus:
    """Overall health status of the Lychee service."""

    healthy: bool
    server_up: bool
    state_store_connected: bool
    workers_alive: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Metrics:
    """Runtime metrics for the Lychee service."""

    uptime_seconds: float
    queue_size: int
    queue_max_size: int
    active_workers: int
    total_workers: int
    jobs_processed: int
    jobs_failed: int
    jobs_in_queue: int


# ---------------------------------------------------------------------------
# Health checker
# ---------------------------------------------------------------------------


class HealthChecker:
    """Checks the health of all Lychee service components."""

    def __init__(
        self,
        state_store: StateStore,
        worker_pool: WorkerPool,
        queue: ReviewQueue,
    ) -> None:
        """Initialize with component references to check.

        Args:
            state_store: The durable state store to verify reachability.
            worker_pool: The worker pool to verify liveness.
            queue: The job queue (currently unused by health checks but
                   available for future extensions).
        """
        self._state_store = state_store
        self._worker_pool = worker_pool
        self._queue = queue

    async def check(self) -> HealthStatus:
        """Run all health checks and return the aggregate status.

        ``healthy`` is ``True`` only if all components are healthy.
        """
        server_up = True  # By definition, if we're responding.
        state_store_connected = await self._check_state_store()
        workers_alive = self._check_workers()

        healthy = server_up and state_store_connected and workers_alive

        details: dict[str, Any] = {
            "server_up": server_up,
            "state_store_connected": state_store_connected,
            "workers_alive": workers_alive,
            "active_workers": self._worker_pool.active_workers,
        }

        if not state_store_connected:
            details["state_store_error"] = "unreachable"
        if not workers_alive:
            details["workers_error"] = "no active workers"

        logger.debug(
            "Health check: healthy=%s details=%s",
            healthy,
            details,
        )

        return HealthStatus(
            healthy=healthy,
            server_up=server_up,
            state_store_connected=state_store_connected,
            workers_alive=workers_alive,
            details=details,
        )

    async def _check_state_store(self) -> bool:
        """Verify the state store is reachable by running a lightweight query."""
        try:
            await self._state_store.list_installations()
            return True
        except Exception:
            logger.warning("State store health check failed", exc_info=True)
            return False

    def _check_workers(self) -> bool:
        """Verify at least one worker is alive."""
        return self._worker_pool.active_workers > 0


# ---------------------------------------------------------------------------
# Metrics collector
# ---------------------------------------------------------------------------


class MetricsCollector:
    """Collects and exposes runtime metrics."""

    def __init__(
        self,
        queue: ReviewQueue,
        worker_pool: WorkerPool,
        start_time: float | None = None,
    ) -> None:
        """Initialize the metrics collector.

        Args:
            queue: The job queue.
            worker_pool: The worker pool.
            start_time: Server start time (Unix timestamp).  Defaults to
                        ``time.time()`` at construction.
        """
        self._queue = queue
        self._worker_pool = worker_pool
        self._start_time = start_time if start_time is not None else time.time()
        self._jobs_processed = 0
        self._jobs_failed = 0

    def collect(self) -> Metrics:
        """Collect current metrics snapshot."""
        return Metrics(
            uptime_seconds=round(time.time() - self._start_time, 3),
            queue_size=self._queue._max_size,
            queue_max_size=self._queue._max_size,
            active_workers=self._worker_pool.active_workers,
            total_workers=self._worker_pool._num_workers,
            jobs_processed=self._jobs_processed,
            jobs_failed=self._jobs_failed,
            jobs_in_queue=self._queue.size,
        )

    def record_job_processed(self) -> None:
        """Increment the processed job counter."""
        self._jobs_processed += 1

    def record_job_failed(self) -> None:
        """Increment the failed job counter."""
        self._jobs_failed += 1
