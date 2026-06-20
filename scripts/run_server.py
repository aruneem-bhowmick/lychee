"""Entrypoint for the Lychee GitHub App webhook server.

Reads required configuration from environment variables, constructs an
``AppConfig``, creates the Starlette ASGI application with the queue,
worker pool, authenticator, state store, health checker, and metrics
collector wired into the webhook server lifecycle, and runs it under
uvicorn.  Exposes ``GET /health`` and ``GET /metrics`` alongside the
webhook endpoint.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import signal
import sys
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from lychee.app_auth import AppAuthenticator
from lychee.config import AppConfig, LycheeConfig, load_config
from lychee.health import HealthChecker, MetricsCollector
from lychee.observability import setup_structured_logging
from lychee.queue import ReviewQueue, WorkerPool, event_to_job
from lychee.state_store import create_state_store
from lychee.webhook import WebhookServer

logger = logging.getLogger(__name__)

# Module-level flag used by the webhook handler to reject new events
# during graceful shutdown.
_draining = False


def load_app_config() -> AppConfig:
    """Load AppConfig from environment variables.

    Required env vars: LYCHEE_WEBHOOK_SECRET, LYCHEE_APP_ID, LYCHEE_PRIVATE_KEY_PATH.
    Raises SystemExit with a clear message if any required var is missing.
    """
    required_vars = ["LYCHEE_WEBHOOK_SECRET", "LYCHEE_APP_ID", "LYCHEE_PRIVATE_KEY_PATH"]
    missing = [v for v in required_vars if not os.environ.get(v)]

    if missing:
        print(
            f"Error: missing required environment variables: {', '.join(sorted(missing))}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return AppConfig(
        webhook_secret=os.environ["LYCHEE_WEBHOOK_SECRET"],
        app_id=int(os.environ["LYCHEE_APP_ID"]),
        private_key_path=os.environ["LYCHEE_PRIVATE_KEY_PATH"],
        host=os.environ.get("LYCHEE_HOST", "0.0.0.0"),
        port=int(os.environ.get("LYCHEE_PORT", "8000")),
        queue_workers=int(os.environ.get("LYCHEE_QUEUE_WORKERS", "4")),
        queue_max_size=int(os.environ.get("LYCHEE_QUEUE_MAX_SIZE", "100")),
        state_backend=os.environ.get("LYCHEE_STATE_BACKEND", "sqlite"),
        state_dsn=os.environ.get("LYCHEE_STATE_DSN", "lychee_state.db"),
    )


def build_server_app(app_config: AppConfig, lychee_config: LycheeConfig) -> Starlette:
    """Build the full server ASGI app with queue, workers, health, and metrics.

    Wires the ``ReviewQueue``, ``AppAuthenticator``, ``SqliteStateStore``,
    ``WorkerPool``, ``HealthChecker``, and ``MetricsCollector`` into the
    ``WebhookServer`` lifecycle.  The ``on_event`` callback converts
    incoming events to jobs and enqueues them.

    On startup the state store is initialised and workers are started.
    On shutdown (triggered by SIGTERM/SIGINT via uvicorn or the lifespan
    context) the server stops accepting new webhooks, workers are drained,
    and the state store is closed.

    Routes:
        POST /webhook  -- GitHub webhook receiver
        GET  /         -- liveness probe
        GET  /health   -- aggregate health check (200 if healthy, 503 if not)
        GET  /metrics  -- runtime metrics snapshot (always 200)

    Args:
        app_config: GitHub App configuration from environment.
        lychee_config: Full Lychee configuration (review settings, model, etc.).

    Returns:
        A Starlette ASGI application ready for uvicorn.
    """
    global _draining  # noqa: PLW0603
    _draining = False

    queue = ReviewQueue(max_size=app_config.queue_max_size)
    authenticator = AppAuthenticator(
        app_id=app_config.app_id,
        private_key_path=app_config.private_key_path,
    )
    state_store = create_state_store(
        backend=app_config.state_backend,
        dsn=app_config.state_dsn,
    )
    worker_pool = WorkerPool(
        queue=queue,
        authenticator=authenticator,
        state_store=state_store,
        config=lychee_config,
        num_workers=app_config.queue_workers,
    )

    start_time = time.time()
    health_checker = HealthChecker(
        state_store=state_store,
        worker_pool=worker_pool,
        queue=queue,
    )
    metrics_collector = MetricsCollector(
        queue=queue,
        worker_pool=worker_pool,
        start_time=start_time,
    )

    async def on_event(event_type: str, payload: dict[str, Any]) -> None:
        """Convert a webhook event to a job and enqueue it."""
        if _draining:
            raise RuntimeError("Server is draining; not accepting new events")
        job = event_to_job(event_type, payload)
        await queue.enqueue(job)

    webhook_server = WebhookServer(
        webhook_secret=app_config.webhook_secret,
        on_event=on_event,
    )

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncGenerator[None]:
        """Initialize resources on startup and tear them down on shutdown."""
        global _draining  # noqa: PLW0603

        logger.info("Server starting: initializing state store and worker pool")
        await state_store.initialize()
        await worker_pool.start()
        logger.info(
            "Server started: workers=%d queue_max=%d",
            app_config.queue_workers,
            app_config.queue_max_size,
        )
        try:
            yield
        finally:
            logger.info("Shutdown initiated: draining queue and stopping workers")
            _draining = True
            await worker_pool.stop(timeout=30)
            await state_store.close()
            logger.info("Server shut down gracefully")

    async def liveness(request: Request) -> Response:
        """Return a simple liveness probe response."""
        return JSONResponse({"service": "lychee", "status": "ok"})

    async def health_endpoint(request: Request) -> Response:
        """Return aggregate health status as JSON (200 or 503)."""
        status = await health_checker.check()
        status_code = 200 if status.healthy else 503
        return JSONResponse(
            {
                "healthy": status.healthy,
                "server_up": status.server_up,
                "state_store_connected": status.state_store_connected,
                "workers_alive": status.workers_alive,
                "details": status.details,
            },
            status_code=status_code,
        )

    async def metrics_endpoint(request: Request) -> Response:
        """Return runtime metrics as JSON (always 200)."""
        snapshot = metrics_collector.collect()
        return JSONResponse(dataclasses.asdict(snapshot), status_code=200)

    return Starlette(
        routes=[
            Route("/webhook", webhook_server.handle_webhook, methods=["POST"]),
            Route("/", liveness, methods=["GET"]),
            Route("/health", health_endpoint, methods=["GET"]),
            Route("/metrics", metrics_endpoint, methods=["GET"]),
        ],
        lifespan=lifespan,
    )


def main() -> None:
    """Load config, create the ASGI app with full queue/worker stack, and run uvicorn."""
    setup_structured_logging()
    app_config = load_app_config()
    lychee_config = load_config()
    app = build_server_app(app_config, lychee_config)
    uvicorn.run(app, host=app_config.host, port=app_config.port)


if __name__ == "__main__":
    main()
