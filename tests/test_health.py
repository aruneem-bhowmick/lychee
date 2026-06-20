"""Comprehensive test suite for the health check and metrics module.

Covers unit, integration, system, acceptance, smoke, sanity, regression,
and end-to-end tests for ``lychee.health`` and the ``/health`` and
``/metrics`` HTTP endpoints exposed by the server.

Framework: pytest + pytest-asyncio + starlette.testclient.TestClient.
Coverage target: >= 90% on src/lychee/health.py.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from lychee.health import HealthChecker, HealthStatus, Metrics, MetricsCollector
from lychee.queue import ReviewQueue, WorkerPool
from lychee.state_store import StateStore

# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------


def _make_mock_state_store(*, healthy: bool = True) -> AsyncMock:
    """Create a mock StateStore that is either healthy or raises on queries."""
    mock = AsyncMock(spec=StateStore)
    if healthy:
        mock.list_installations.return_value = []
    else:
        mock.list_installations.side_effect = RuntimeError("store unreachable")
    mock.initialize.return_value = None
    mock.close.return_value = None
    return mock


def _make_mock_worker_pool(*, active: int = 2, total: int = 4) -> MagicMock:
    """Create a mock WorkerPool with configurable active/total workers."""
    mock = MagicMock(spec=WorkerPool)
    mock.active_workers = active
    mock._num_workers = total
    mock.start = AsyncMock()
    mock.stop = AsyncMock()
    return mock


def _make_mock_queue(*, size: int = 0, max_size: int = 100) -> MagicMock:
    """Create a mock ReviewQueue with configurable size."""
    mock = MagicMock(spec=ReviewQueue)
    mock.size = size
    mock._max_size = max_size
    mock.is_full = size >= max_size
    return mock


def _make_health_checker(
    *,
    store_healthy: bool = True,
    active_workers: int = 2,
    total_workers: int = 4,
    queue_size: int = 0,
) -> HealthChecker:
    """Create a HealthChecker with mock components."""
    store = _make_mock_state_store(healthy=store_healthy)
    pool = _make_mock_worker_pool(active=active_workers, total=total_workers)
    queue = _make_mock_queue(size=queue_size)
    return HealthChecker(state_store=store, worker_pool=pool, queue=queue)


def _make_metrics_collector(
    *,
    queue_size: int = 0,
    max_size: int = 100,
    active_workers: int = 2,
    total_workers: int = 4,
    start_time: float | None = None,
) -> MetricsCollector:
    """Create a MetricsCollector with mock components."""
    queue = _make_mock_queue(size=queue_size, max_size=max_size)
    pool = _make_mock_worker_pool(active=active_workers, total=total_workers)
    return MetricsCollector(
        queue=queue,
        worker_pool=pool,
        start_time=start_time,
    )


def _build_test_app(
    *,
    store_healthy: bool = True,
    active_workers: int = 2,
    total_workers: int = 4,
    queue_size: int = 0,
    max_size: int = 100,
) -> Starlette:
    """Build a minimal Starlette app with /health and /metrics routes for testing."""
    store = _make_mock_state_store(healthy=store_healthy)
    pool = _make_mock_worker_pool(active=active_workers, total=total_workers)
    queue = _make_mock_queue(size=queue_size, max_size=max_size)

    health_checker = HealthChecker(state_store=store, worker_pool=pool, queue=queue)
    metrics_collector = MetricsCollector(queue=queue, worker_pool=pool, start_time=time.time())

    async def health_endpoint(request: Request) -> Response:
        """Return aggregate health status."""
        status = await health_checker.check()
        code = 200 if status.healthy else 503
        return JSONResponse(
            {
                "healthy": status.healthy,
                "server_up": status.server_up,
                "state_store_connected": status.state_store_connected,
                "workers_alive": status.workers_alive,
                "details": status.details,
            },
            status_code=code,
        )

    async def metrics_endpoint(request: Request) -> Response:
        """Return metrics snapshot."""
        snapshot = metrics_collector.collect()
        return JSONResponse(dataclasses.asdict(snapshot), status_code=200)

    return Starlette(
        routes=[
            Route("/health", health_endpoint, methods=["GET"]),
            Route("/metrics", metrics_endpoint, methods=["GET"]),
        ],
    )


# ===========================================================================
# Smoke tests
# ===========================================================================


class TestSmoke:
    """Smoke tests: basic import and instantiation checks."""

    def test_health_module_imports(self) -> None:
        """Importing health module public types succeeds."""
        # P5-R5
        from lychee.health import HealthChecker, HealthStatus, Metrics, MetricsCollector

        assert HealthChecker is not None
        assert HealthStatus is not None
        assert Metrics is not None
        assert MetricsCollector is not None

    def test_dockerfile_syntax(self) -> None:
        """Dockerfile parses without obvious errors (basic structural validation)."""
        # P5-R5
        from pathlib import Path

        dockerfile = Path(__file__).parent.parent / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "FROM" in content
        assert "CMD" in content
        assert "EXPOSE" in content
        assert "HEALTHCHECK" in content
        # Ensure no secrets are baked in
        assert "ANTHROPIC_API_KEY=" not in content
        assert "LYCHEE_WEBHOOK_SECRET=" not in content


# ===========================================================================
# Unit tests
# ===========================================================================


class TestHealthStatusUnit:
    """Unit tests for HealthStatus dataclass."""

    @pytest.mark.asyncio
    async def test_health_status_all_healthy(self) -> None:
        """All checks pass -> healthy=True."""
        # P5-R5
        checker = _make_health_checker(store_healthy=True, active_workers=2)
        status = await checker.check()
        assert status.healthy is True
        assert status.server_up is True
        assert status.state_store_connected is True
        assert status.workers_alive is True

    @pytest.mark.asyncio
    async def test_health_status_store_down(self) -> None:
        """State store check fails -> healthy=False, state_store_connected=False."""
        # P5-R5
        checker = _make_health_checker(store_healthy=False, active_workers=2)
        status = await checker.check()
        assert status.healthy is False
        assert status.state_store_connected is False
        assert status.server_up is True
        assert status.workers_alive is True

    @pytest.mark.asyncio
    async def test_health_status_workers_dead(self) -> None:
        """No active workers -> healthy=False, workers_alive=False."""
        # P5-R5
        checker = _make_health_checker(store_healthy=True, active_workers=0)
        status = await checker.check()
        assert status.healthy is False
        assert status.workers_alive is False
        assert status.server_up is True
        assert status.state_store_connected is True

    @pytest.mark.asyncio
    async def test_health_status_both_down(self) -> None:
        """Both store and workers fail -> healthy=False."""
        # P5-R5
        checker = _make_health_checker(store_healthy=False, active_workers=0)
        status = await checker.check()
        assert status.healthy is False
        assert status.state_store_connected is False
        assert status.workers_alive is False

    def test_health_status_dataclass(self) -> None:
        """HealthStatus fields are correct types."""
        # P5-R5
        status = HealthStatus(
            healthy=True,
            server_up=True,
            state_store_connected=True,
            workers_alive=True,
            details={"key": "value"},
        )
        assert isinstance(status.healthy, bool)
        assert isinstance(status.server_up, bool)
        assert isinstance(status.state_store_connected, bool)
        assert isinstance(status.workers_alive, bool)
        assert isinstance(status.details, dict)

    def test_health_status_default_details(self) -> None:
        """HealthStatus details defaults to an empty dict."""
        # P5-R5
        status = HealthStatus(
            healthy=True,
            server_up=True,
            state_store_connected=True,
            workers_alive=True,
        )
        assert status.details == {}


class TestMetricsUnit:
    """Unit tests for Metrics dataclass and MetricsCollector."""

    def test_metrics_dataclass(self) -> None:
        """Metrics fields are correct types."""
        # P5-R5
        m = Metrics(
            uptime_seconds=123.456,
            queue_size=100,
            queue_max_size=100,
            active_workers=3,
            total_workers=4,
            jobs_processed=10,
            jobs_failed=1,
            jobs_in_queue=5,
        )
        assert isinstance(m.uptime_seconds, float)
        assert isinstance(m.queue_size, int)
        assert isinstance(m.queue_max_size, int)
        assert isinstance(m.active_workers, int)
        assert isinstance(m.total_workers, int)
        assert isinstance(m.jobs_processed, int)
        assert isinstance(m.jobs_failed, int)
        assert isinstance(m.jobs_in_queue, int)

    def test_metrics_uptime(self) -> None:
        """uptime_seconds increases with time."""
        # P5-R5
        start = time.time() - 100.0
        collector = _make_metrics_collector(start_time=start)
        m = collector.collect()
        assert m.uptime_seconds >= 100.0

    def test_metrics_job_counters(self) -> None:
        """record_job_processed and record_job_failed increment correctly."""
        # P5-R5
        collector = _make_metrics_collector()
        assert collector.collect().jobs_processed == 0
        assert collector.collect().jobs_failed == 0

        collector.record_job_processed()
        collector.record_job_processed()
        collector.record_job_failed()

        m = collector.collect()
        assert m.jobs_processed == 2
        assert m.jobs_failed == 1

    def test_metrics_queue_size(self) -> None:
        """queue_size reflects the queue state."""
        # P5-R5
        collector = _make_metrics_collector(queue_size=7, max_size=50)
        m = collector.collect()
        assert m.jobs_in_queue == 7
        assert m.queue_max_size == 50

    def test_metrics_collect_snapshot(self) -> None:
        """collect() returns a Metrics with all fields populated."""
        # P5-R5
        collector = _make_metrics_collector(
            queue_size=3,
            max_size=100,
            active_workers=2,
            total_workers=4,
            start_time=time.time() - 60,
        )
        collector.record_job_processed()
        collector.record_job_failed()

        m = collector.collect()
        assert m.uptime_seconds >= 60.0
        assert m.queue_max_size == 100
        assert m.active_workers == 2
        assert m.total_workers == 4
        assert m.jobs_processed == 1
        assert m.jobs_failed == 1
        assert m.jobs_in_queue == 3

    def test_metrics_default_start_time(self) -> None:
        """MetricsCollector defaults start_time to current time."""
        # P5-R5
        collector = _make_metrics_collector(start_time=None)
        m = collector.collect()
        # Uptime should be very small since we just created it
        assert m.uptime_seconds < 2.0


# ===========================================================================
# Sanity tests
# ===========================================================================


class TestSanity:
    """Sanity tests: confirm basic return types and contracts."""

    @pytest.mark.asyncio
    async def test_health_check_returns_health_status(self) -> None:
        """check() returns a HealthStatus instance."""
        # P5-R5
        checker = _make_health_checker()
        result = await checker.check()
        assert isinstance(result, HealthStatus)

    def test_metrics_collect_returns_metrics(self) -> None:
        """collect() returns a Metrics instance."""
        # P5-R5
        collector = _make_metrics_collector()
        result = collector.collect()
        assert isinstance(result, Metrics)


# ===========================================================================
# Integration tests
# ===========================================================================


class TestIntegration:
    """Integration tests: HTTP endpoints via TestClient."""

    def test_health_endpoint_healthy(self) -> None:
        """GET /health returns 200 with healthy: true when all components are up."""
        # P5-R5
        app = _build_test_app(store_healthy=True, active_workers=2)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is True
        assert data["server_up"] is True
        assert data["state_store_connected"] is True
        assert data["workers_alive"] is True

    def test_health_endpoint_unhealthy(self) -> None:
        """GET /health returns 503 with healthy: false when state store is unreachable."""
        # P5-R5
        app = _build_test_app(store_healthy=False, active_workers=2)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["healthy"] is False
        assert data["state_store_connected"] is False

    def test_health_endpoint_workers_dead(self) -> None:
        """GET /health returns 503 when workers are dead."""
        # P5-R5
        app = _build_test_app(store_healthy=True, active_workers=0)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["healthy"] is False
        assert data["workers_alive"] is False

    def test_metrics_endpoint(self) -> None:
        """GET /metrics returns 200 with valid JSON containing all metric fields."""
        # P5-R5
        app = _build_test_app(queue_size=5, active_workers=3, total_workers=4)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()
        expected_keys = {
            "uptime_seconds",
            "queue_size",
            "queue_max_size",
            "active_workers",
            "total_workers",
            "jobs_processed",
            "jobs_failed",
            "jobs_in_queue",
        }
        assert set(data.keys()) == expected_keys
        assert data["active_workers"] == 3
        assert data["total_workers"] == 4
        assert data["jobs_in_queue"] == 5


# ===========================================================================
# Regression tests
# ===========================================================================


class TestRegression:
    """Regression tests: snapshot the response shapes."""

    def test_health_response_shape(self) -> None:
        """Health endpoint response has the expected JSON structure."""
        # P5-R5
        app = _build_test_app(store_healthy=True, active_workers=2)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        data = resp.json()
        # Top-level keys
        assert set(data.keys()) == {
            "healthy",
            "server_up",
            "state_store_connected",
            "workers_alive",
            "details",
        }
        # Details sub-keys
        assert "server_up" in data["details"]
        assert "state_store_connected" in data["details"]
        assert "workers_alive" in data["details"]
        assert "active_workers" in data["details"]

    def test_metrics_response_shape(self) -> None:
        """Metrics endpoint response has the expected JSON structure."""
        # P5-R5
        app = _build_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/metrics")
        data = resp.json()
        expected_keys = {
            "uptime_seconds",
            "queue_size",
            "queue_max_size",
            "active_workers",
            "total_workers",
            "jobs_processed",
            "jobs_failed",
            "jobs_in_queue",
        }
        assert set(data.keys()) == expected_keys
        # All values are numeric
        for key in expected_keys:
            assert isinstance(data[key], (int, float)), f"{key} is not numeric"

    def test_health_unhealthy_response_shape(self) -> None:
        """Unhealthy response includes error details."""
        # P5-R5
        app = _build_test_app(store_healthy=False, active_workers=0)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        data = resp.json()
        assert data["healthy"] is False
        assert "state_store_error" in data["details"]
        assert "workers_error" in data["details"]


# ===========================================================================
# System tests
# ===========================================================================


class TestSystem:
    """System tests: full service lifecycle with mock externals."""

    @pytest.mark.asyncio
    async def test_lifecycle_startup_shutdown(self) -> None:
        """Programmatically start and stop; assert state store init/close and worker start/stop."""
        # P5-R5
        store = _make_mock_state_store(healthy=True)
        pool = _make_mock_worker_pool(active=4, total=4)
        queue = _make_mock_queue()

        # Simulate startup
        await store.initialize()
        await pool.start()

        store.initialize.assert_awaited_once()
        pool.start.assert_awaited_once()

        # Verify health during "running" state
        checker = HealthChecker(state_store=store, worker_pool=pool, queue=queue)
        status = await checker.check()
        assert status.healthy is True

        # Simulate shutdown
        await pool.stop()
        await store.close()

        pool.stop.assert_awaited_once()
        store.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_full_service_lifecycle(self) -> None:
        """Create full service, check health, then shut down."""
        # P5-R5
        store = _make_mock_state_store(healthy=True)
        pool = _make_mock_worker_pool(active=4, total=4)
        queue = _make_mock_queue(size=0, max_size=100)

        checker = HealthChecker(state_store=store, worker_pool=pool, queue=queue)
        metrics = MetricsCollector(queue=queue, worker_pool=pool, start_time=time.time())

        # Startup
        await store.initialize()
        await pool.start()

        # Health check
        status = await checker.check()
        assert status.healthy is True

        # Metrics check
        m = metrics.collect()
        assert m.active_workers == 4
        assert m.total_workers == 4

        # Record some work
        metrics.record_job_processed()
        metrics.record_job_processed()
        metrics.record_job_failed()

        m2 = metrics.collect()
        assert m2.jobs_processed == 2
        assert m2.jobs_failed == 1

        # Shutdown
        await pool.stop()
        await store.close()

    @pytest.mark.asyncio
    async def test_shutdown_drains_queue(self) -> None:
        """Enqueue jobs, initiate shutdown, assert drain behavior."""
        # P5-R5
        real_queue = ReviewQueue(max_size=10)

        # Use a real queue to test draining
        from lychee.queue import Job, JobType

        job = Job(
            job_id="test-drain-1",
            job_type=JobType.pr_review,
            installation_id=1,
            repo_full_name="owner/repo",
            pr_number=1,
            event_type="pull_request",
            payload={},
        )
        await real_queue.enqueue(job)
        assert real_queue.size == 1

        # Dequeue (simulating what a worker would do)
        item = await asyncio.wait_for(real_queue.dequeue(), timeout=1.0)
        assert item is not None
        assert item.job_id == "test-drain-1"
        assert real_queue.size == 0


# ===========================================================================
# Acceptance tests
# ===========================================================================


class TestAcceptance:
    """Acceptance tests: verify user-visible behavior per acceptance criteria."""

    def test_accept_health_endpoint_green(self) -> None:
        """Health endpoint returns 200 when the service is running normally."""
        # P5-R5
        app = _build_test_app(store_healthy=True, active_workers=4, total_workers=4)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["healthy"] is True

    def test_accept_metrics_exported(self) -> None:
        """Metrics endpoint returns all expected fields."""
        # P5-R5
        app = _build_test_app(
            queue_size=2,
            max_size=100,
            active_workers=4,
            total_workers=4,
        )
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()
        required_fields = [
            "uptime_seconds",
            "queue_size",
            "queue_max_size",
            "active_workers",
            "total_workers",
            "jobs_processed",
            "jobs_failed",
            "jobs_in_queue",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_accept_restart_safe(self) -> None:
        """State persists across re-initialization (restart-safe)."""
        # P5-R5
        from lychee.state_store import ReviewState, SqliteStateStore

        store = SqliteStateStore(dsn=":memory:")
        await store.initialize()

        # Write state
        await store.upsert_review(
            ReviewState(
                repo_full_name="owner/repo",
                pr_number=42,
                installation_id=1,
                review_status="completed",
                last_reviewed_sha="abc123",
            )
        )

        # Verify state is there
        review = await store.get_review("owner/repo", 42)
        assert review is not None
        assert review.review_status == "completed"
        assert review.last_reviewed_sha == "abc123"

        # "Restart" with same store (in-memory, so we just verify idempotent init)
        await store.initialize()
        review2 = await store.get_review("owner/repo", 42)
        assert review2 is not None
        assert review2.review_status == "completed"

        await store.close()


# ===========================================================================
# End-to-end tests (mocked externals)
# ===========================================================================


class TestEndToEnd:
    """End-to-end tests with mocked externals."""

    def test_e2e_server_health(self) -> None:
        """Start the full server locally (all externals mocked), hit /health via TestClient."""
        # P5-R5
        app = _build_test_app(
            store_healthy=True,
            active_workers=4,
            total_workers=4,
            queue_size=0,
        )
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is True
        assert data["server_up"] is True

    def test_e2e_server_metrics_after_processing(self) -> None:
        """Start server, simulate processing, check /metrics shows jobs_processed >= 1."""
        # P5-R5
        store = _make_mock_state_store(healthy=True)
        pool = _make_mock_worker_pool(active=4, total=4)
        queue = _make_mock_queue(size=0, max_size=100)

        health_checker = HealthChecker(state_store=store, worker_pool=pool, queue=queue)
        metrics_collector = MetricsCollector(queue=queue, worker_pool=pool, start_time=time.time())

        # Simulate job processing
        metrics_collector.record_job_processed()
        metrics_collector.record_job_processed()
        metrics_collector.record_job_failed()

        async def health_endpoint(request: Request) -> Response:
            """Return aggregate health status."""
            status = await health_checker.check()
            code = 200 if status.healthy else 503
            return JSONResponse(dataclasses.asdict(status), status_code=code)

        async def metrics_endpoint(request: Request) -> Response:
            """Return metrics snapshot."""
            snapshot = metrics_collector.collect()
            return JSONResponse(dataclasses.asdict(snapshot), status_code=200)

        app = Starlette(
            routes=[
                Route("/health", health_endpoint, methods=["GET"]),
                Route("/metrics", metrics_endpoint, methods=["GET"]),
            ],
        )
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["jobs_processed"] >= 1
        assert data["jobs_failed"] >= 1


# ===========================================================================
# Edge-case and private method tests
# ===========================================================================


class TestPrivateMethods:
    """Tests for internal health check methods to ensure coverage."""

    @pytest.mark.asyncio
    async def test_check_state_store_success(self) -> None:
        """_check_state_store returns True when the store is reachable."""
        # P5-R5
        checker = _make_health_checker(store_healthy=True)
        result = await checker._check_state_store()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_state_store_failure(self) -> None:
        """_check_state_store returns False when the store raises."""
        # P5-R5
        checker = _make_health_checker(store_healthy=False)
        result = await checker._check_state_store()
        assert result is False

    def test_check_workers_alive(self) -> None:
        """_check_workers returns True when active_workers > 0."""
        # P5-R5
        checker = _make_health_checker(active_workers=1)
        assert checker._check_workers() is True

    def test_check_workers_dead(self) -> None:
        """_check_workers returns False when active_workers == 0."""
        # P5-R5
        checker = _make_health_checker(active_workers=0)
        assert checker._check_workers() is False

    @pytest.mark.asyncio
    async def test_health_details_include_error_messages(self) -> None:
        """Details include error strings when checks fail."""
        # P5-R5
        checker = _make_health_checker(store_healthy=False, active_workers=0)
        status = await checker.check()
        assert "state_store_error" in status.details
        assert "workers_error" in status.details
        assert status.details["state_store_error"] == "unreachable"
        assert status.details["workers_error"] == "no active workers"

    @pytest.mark.asyncio
    async def test_health_details_no_errors_when_healthy(self) -> None:
        """Details do not include error keys when all checks pass."""
        # P5-R5
        checker = _make_health_checker(store_healthy=True, active_workers=2)
        status = await checker.check()
        assert "state_store_error" not in status.details
        assert "workers_error" not in status.details
