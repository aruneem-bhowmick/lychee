"""Async webhook server for receiving GitHub App events.

Receives GitHub webhook HTTP POST requests, verifies their HMAC-SHA256
signatures against the configured webhook secret, filters for applicable
events (pull_request and issue_comment), and delegates processing to an
optional async callback.  Non-applicable events are acknowledged and
discarded.  The server is designed for fast-ack within the GitHub timeout
(< 10 s); the callback must enqueue work and return promptly.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Awaitable, Callable

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from lychee.config import AppConfig
from lychee.observability import new_correlation_id

logger = logging.getLogger(__name__)

_APPLICABLE_PR_ACTIONS = frozenset({"opened", "synchronize", "reopened"})


class WebhookServer:
    """Async webhook server for receiving GitHub App events."""

    def __init__(
        self,
        webhook_secret: str,
        on_event: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize with webhook secret and optional event callback.

        Args:
            webhook_secret: HMAC-SHA256 secret for signature verification.
            on_event: Async callback invoked with (event_type, payload) after
                      validation. If None, events are logged and discarded.
        """
        self._webhook_secret = webhook_secret
        self._on_event = on_event

    def verify_signature(self, body: bytes, signature: str) -> bool:
        """Verify the HMAC-SHA256 signature of a webhook payload.

        Args:
            body: Raw request body bytes.
            signature: Value of the X-Hub-Signature-256 header (e.g., ``sha256=abc...``).

        Returns:
            True if the signature is valid; False otherwise.
        """
        if not signature.startswith("sha256="):
            return False
        expected = hmac.new(
            self._webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature[len("sha256=") :])

    def is_applicable_event(self, event_type: str, payload: dict[str, Any]) -> bool:
        """Return True if this event should be processed by Lychee.

        Applicable events:
        - pull_request with action in {opened, synchronize, reopened}
        - issue_comment with action created, on a PR (payload has issue.pull_request)
        """
        if event_type == "pull_request":
            return payload.get("action") in _APPLICABLE_PR_ACTIONS
        if event_type == "issue_comment":
            if payload.get("action") != "created":
                return False
            issue = payload.get("issue", {})
            return bool(issue.get("pull_request"))
        return False

    async def handle_webhook(self, request: Request) -> Response:
        """Handle an incoming webhook request.

        1. Read body and verify signature; reject with 403 if invalid.
        2. Parse JSON payload and extract event type from X-GitHub-Event header.
        3. If not applicable, return 200 with {"status": "ignored"}.
        4. If applicable, invoke on_event callback (if set) and return 202 with
           {"status": "accepted"}.
        5. On any processing error, return 500 with {"status": "error"}.
        """
        correlation_id = new_correlation_id()

        try:
            body = await request.body()
            signature = request.headers.get("X-Hub-Signature-256", "")
            event_type = request.headers.get("X-GitHub-Event", "")

            if not self.verify_signature(body, signature):
                logger.warning(
                    "Webhook signature verification failed (correlation_id=%s)",
                    correlation_id,
                )
                return JSONResponse({"status": "forbidden"}, status_code=403)

            payload: dict[str, Any] = json.loads(body)

            if not self.is_applicable_event(event_type, payload):
                logger.info(
                    "Ignoring non-applicable event type=%s (correlation_id=%s)",
                    event_type,
                    correlation_id,
                )
                return JSONResponse({"status": "ignored"}, status_code=200)

            logger.info(
                "Accepted webhook event type=%s (correlation_id=%s)",
                event_type,
                correlation_id,
            )

            if self._on_event is not None:
                try:
                    await self._on_event(event_type, payload)
                except Exception:
                    logger.exception(
                        "Event callback raised an error (correlation_id=%s)",
                        correlation_id,
                    )
                    return JSONResponse({"status": "error"}, status_code=500)

            return JSONResponse({"status": "accepted"}, status_code=202)

        except Exception:
            logger.exception(
                "Unexpected error processing webhook (correlation_id=%s)",
                correlation_id,
            )
            return JSONResponse({"status": "error"}, status_code=500)

    def create_app(self) -> Starlette:
        """Create and return the Starlette ASGI application."""

        async def liveness(request: Request) -> Response:
            """Return a simple liveness probe response."""
            return JSONResponse({"service": "lychee", "status": "ok"})

        return Starlette(
            routes=[
                Route("/webhook", self.handle_webhook, methods=["POST"]),
                Route("/", liveness, methods=["GET"]),
            ],
        )


def create_webhook_app(config: AppConfig) -> Starlette:
    """Factory function: create a configured WebhookServer and return its ASGI app.

    Args:
        config: App configuration with webhook_secret, host, port.

    Returns:
        A Starlette ASGI application ready to be served by uvicorn.
    """
    server = WebhookServer(webhook_secret=config.webhook_secret)
    return server.create_app()
