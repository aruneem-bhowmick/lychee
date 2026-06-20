"""Entrypoint for the Lychee GitHub App webhook server.

Reads required configuration from environment variables, constructs an
``AppConfig``, creates the Starlette ASGI application with the queue,
worker pool, authenticator, and state store wired into the webhook
server lifecycle, and runs it under uvicorn.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from lychee.app_auth import AppAuthenticator
from lychee.config import AppConfig, LycheeConfig, load_config
from lychee.observability import setup_structured_logging
from lychee.queue import ReviewQueue, WorkerPool, event_to_job
from lychee.state_store import create_state_store
from lychee.webhook import WebhookServer

logger = logging.getLogger(__name__)


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
    """Build the full server ASGI app with queue, workers, and state store.

    Wires the ``ReviewQueue``, ``AppAuthenticator``, ``SqliteStateStore``,
    and ``WorkerPool`` into the ``WebhookServer`` lifecycle.  The
    ``on_event`` callback converts incoming events to jobs and enqueues
    them.  On startup the state store is initialised and workers are
    started; on shutdown workers are stopped and the state store is closed.

    Args:
        app_config: GitHub App configuration from environment.
        lychee_config: Full Lychee configuration (review settings, model, etc.).

    Returns:
        A Starlette ASGI application ready for uvicorn.
    """
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

    async def on_event(event_type: str, payload: dict[str, Any]) -> None:
        """Convert a webhook event to a job and enqueue it."""
        job = event_to_job(event_type, payload)
        await queue.enqueue(job)

    webhook_server = WebhookServer(
        webhook_secret=app_config.webhook_secret,
        on_event=on_event,
    )

    async def startup() -> None:
        """Initialize the state store and start the worker pool."""
        await state_store.initialize()
        await worker_pool.start()
        logger.info("Server started: workers=%d queue_max=%d",
                     app_config.queue_workers, app_config.queue_max_size)

    async def shutdown() -> None:
        """Stop workers and close the state store."""
        await worker_pool.stop()
        await state_store.close()
        logger.info("Server shut down gracefully")

    async def liveness(request: Request) -> Response:
        """Return a simple liveness probe response."""
        return JSONResponse({"service": "lychee", "status": "ok"})

    return Starlette(
        routes=[
            Route("/webhook", webhook_server.handle_webhook, methods=["POST"]),
            Route("/", liveness, methods=["GET"]),
        ],
        on_startup=[startup],
        on_shutdown=[shutdown],
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
