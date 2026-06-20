"""Unit, integration, system, acceptance, smoke, sanity, regression, and API tests
for the webhook server module.

Covers HMAC-SHA256 signature verification, event filtering, the full request
lifecycle through the Starlette ASGI application, callback invocation, error
handling, and response shapes.

Framework: pytest + starlette.testclient.TestClient.
Coverage target: >= 90% on src/lychee/webhook.py.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from lychee.config import AppConfig
from lychee.webhook import WebhookServer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SECRET = "test-webhook-secret"


def _sign(body: bytes, secret: str = SECRET) -> str:
    """Compute a valid X-Hub-Signature-256 header value."""
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _make_server(
    on_event: Any = None,
    secret: str = SECRET,
) -> WebhookServer:
    """Create a WebhookServer with the test secret."""
    return WebhookServer(webhook_secret=secret, on_event=on_event)


def _make_client(
    on_event: Any = None,
    secret: str = SECRET,
) -> TestClient:
    """Create a Starlette TestClient wrapping a WebhookServer."""
    server = _make_server(on_event=on_event, secret=secret)
    app = server.create_app()
    return TestClient(app, raise_server_exceptions=False)


def _pr_payload(action: str = "opened") -> dict[str, Any]:
    """Minimal pull_request webhook payload."""
    return {"action": action, "pull_request": {"number": 1}}


def _issue_comment_payload(
    action: str = "created",
    on_pr: bool = True,
) -> dict[str, Any]:
    """Minimal issue_comment webhook payload."""
    issue: dict[str, Any] = {"number": 1}
    if on_pr:
        issue["pull_request"] = {"url": "https://api.github.com/repos/o/r/pulls/1"}
    return {"action": action, "issue": issue}


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_webhook_module_imports() -> None:
    """from lychee.webhook import WebhookServer, create_webhook_app succeeds."""
    from lychee.webhook import WebhookServer, create_webhook_app

    assert WebhookServer is not None
    assert create_webhook_app is not None


def test_run_server_module_imports() -> None:
    """from scripts.run_server import main, load_app_config succeeds."""
    from scripts.run_server import load_app_config, main

    assert main is not None
    assert load_app_config is not None


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_webhook_app_is_starlette() -> None:
    """create_app() returns a Starlette instance."""
    server = _make_server()
    app = server.create_app()
    assert isinstance(app, Starlette)


def test_config_still_loads_without_app() -> None:
    """Existing load_config() works when no 'app' key is present."""
    from lychee.config import LycheeConfig

    config = LycheeConfig()
    assert config.app is None


# ---------------------------------------------------------------------------
# Unit tests — signature verification
# ---------------------------------------------------------------------------


def test_verify_signature_valid() -> None:
    """A correct HMAC-SHA256 signature passes verification."""
    server = _make_server()
    body = b'{"action":"opened"}'
    sig = _sign(body)
    assert server.verify_signature(body, sig) is True


def test_verify_signature_invalid() -> None:
    """A wrong HMAC-SHA256 signature fails verification."""
    server = _make_server()
    body = b'{"action":"opened"}'
    assert server.verify_signature(body, "sha256=0000bad") is False


def test_verify_signature_missing_prefix() -> None:
    """A signature without the 'sha256=' prefix fails verification."""
    server = _make_server()
    body = b'{"action":"opened"}'
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert server.verify_signature(body, digest) is False


def test_verify_signature_empty() -> None:
    """An empty signature string fails verification."""
    server = _make_server()
    assert server.verify_signature(b"body", "") is False


# ---------------------------------------------------------------------------
# Unit tests — event filtering
# ---------------------------------------------------------------------------


def test_is_applicable_pr_opened() -> None:
    """pull_request with action 'opened' is applicable."""
    server = _make_server()
    assert server.is_applicable_event("pull_request", _pr_payload("opened")) is True


def test_is_applicable_pr_synchronize() -> None:
    """pull_request with action 'synchronize' is applicable."""
    server = _make_server()
    assert server.is_applicable_event("pull_request", _pr_payload("synchronize")) is True


def test_is_applicable_pr_reopened() -> None:
    """pull_request with action 'reopened' is applicable."""
    server = _make_server()
    assert server.is_applicable_event("pull_request", _pr_payload("reopened")) is True


def test_is_applicable_pr_closed() -> None:
    """pull_request with action 'closed' is NOT applicable."""
    server = _make_server()
    assert server.is_applicable_event("pull_request", _pr_payload("closed")) is False


def test_is_applicable_issue_comment_on_pr() -> None:
    """issue_comment with action 'created' on a PR is applicable."""
    server = _make_server()
    payload = _issue_comment_payload(action="created", on_pr=True)
    assert server.is_applicable_event("issue_comment", payload) is True


def test_is_applicable_issue_comment_on_issue() -> None:
    """issue_comment with action 'created' on a plain issue is NOT applicable."""
    server = _make_server()
    payload = _issue_comment_payload(action="created", on_pr=False)
    assert server.is_applicable_event("issue_comment", payload) is False


def test_is_applicable_issue_comment_deleted() -> None:
    """issue_comment with action 'deleted' is NOT applicable."""
    server = _make_server()
    payload = _issue_comment_payload(action="deleted", on_pr=True)
    assert server.is_applicable_event("issue_comment", payload) is False


def test_is_applicable_unknown_event() -> None:
    """An unknown event type like 'push' is NOT applicable."""
    server = _make_server()
    assert server.is_applicable_event("push", {"action": "completed"}) is False


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_webhook_endpoint_valid_signature() -> None:
    """POST /webhook with valid signature and applicable event returns 202."""
    client = _make_client()
    body = json.dumps(_pr_payload("opened")).encode()
    sig = _sign(body)
    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted"}


def test_webhook_endpoint_invalid_signature() -> None:
    """POST /webhook with invalid signature returns 403."""
    client = _make_client()
    body = json.dumps(_pr_payload("opened")).encode()
    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": "sha256=invalid",
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 403
    assert resp.json() == {"status": "forbidden"}


def test_webhook_endpoint_ignored_event() -> None:
    """POST /webhook with valid signature but non-applicable event returns 200."""
    client = _make_client()
    body = json.dumps({"action": "closed", "pull_request": {"number": 1}}).encode()
    sig = _sign(body)
    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored"}


def test_webhook_endpoint_callback_invoked() -> None:
    """When on_event is set, it receives the event type and parsed payload."""
    callback = AsyncMock()
    client = _make_client(on_event=callback)

    payload = _pr_payload("opened")
    body = json.dumps(payload).encode()
    sig = _sign(body)
    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 202
    callback.assert_awaited_once_with("pull_request", payload)


def test_webhook_endpoint_callback_error() -> None:
    """When on_event raises, server returns 500 without crashing."""
    callback = AsyncMock(side_effect=RuntimeError("boom"))
    client = _make_client(on_event=callback)

    payload = _pr_payload("opened")
    body = json.dumps(payload).encode()
    sig = _sign(body)
    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 500
    assert resp.json() == {"status": "error"}


def test_webhook_liveness_endpoint() -> None:
    """GET / returns 200 with liveness payload."""
    client = _make_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"service": "lychee", "status": "ok"}


# ---------------------------------------------------------------------------
# System tests
# ---------------------------------------------------------------------------


def test_webhook_full_flow() -> None:
    """Full flow: create app via factory, send valid PR webhook, assert callback fires."""
    callback = AsyncMock()
    config = AppConfig(
        webhook_secret=SECRET,
        app_id=42,
        private_key_path="/tmp/key.pem",
    )
    # Manually wire callback via the server rather than the factory (factory
    # doesn't expose on_event).
    server = WebhookServer(webhook_secret=config.webhook_secret, on_event=callback)
    app = server.create_app()
    client = TestClient(app, raise_server_exceptions=False)

    payload = _pr_payload("opened")
    body = json.dumps(payload).encode()
    sig = _sign(body, secret=config.webhook_secret)
    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted"}
    callback.assert_awaited_once_with("pull_request", payload)


def test_webhook_rejects_then_accepts() -> None:
    """Send invalid-signature request then valid; first rejected, second accepted."""
    client = _make_client()

    payload = _pr_payload("opened")
    body = json.dumps(payload).encode()

    # First request: bad signature → 403
    resp1 = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": "sha256=bad",
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp1.status_code == 403

    # Second request: valid signature → 202
    sig = _sign(body)
    resp2 = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp2.status_code == 202


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_valid_webhooks_acked() -> None:
    """Valid webhooks receive HTTP 2xx (202 for applicable, 200 for ignored)."""
    client = _make_client()

    # Applicable event → 202
    body_app = json.dumps(_pr_payload("opened")).encode()
    resp_app = client.post(
        "/webhook",
        content=body_app,
        headers={
            "X-Hub-Signature-256": _sign(body_app),
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert 200 <= resp_app.status_code < 300

    # Ignored event → 200
    body_ign = json.dumps({"action": "closed", "pull_request": {"number": 1}}).encode()
    resp_ign = client.post(
        "/webhook",
        content=body_ign,
        headers={
            "X-Hub-Signature-256": _sign(body_ign),
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert 200 <= resp_ign.status_code < 300


def test_accept_invalid_signatures_rejected() -> None:
    """Invalid signatures receive 403."""
    client = _make_client()
    body = json.dumps(_pr_payload("opened")).encode()
    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": "sha256=wrong",
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Regression tests — parametrized snapshots
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body,secret,signature_hex,expected_valid",
    [
        # Known-good pair
        (
            b'{"action":"opened"}',
            "s3cret",
            hmac.new(b"s3cret", b'{"action":"opened"}', hashlib.sha256).hexdigest(),
            True,
        ),
        # Wrong secret
        (
            b'{"action":"opened"}',
            "s3cret",
            hmac.new(b"other", b'{"action":"opened"}', hashlib.sha256).hexdigest(),
            False,
        ),
        # Empty body
        (
            b"",
            "key",
            hmac.new(b"key", b"", hashlib.sha256).hexdigest(),
            True,
        ),
        # Tampered body
        (
            b'{"action":"closed"}',
            "key",
            hmac.new(b"key", b'{"action":"opened"}', hashlib.sha256).hexdigest(),
            False,
        ),
    ],
    ids=["known-good", "wrong-secret", "empty-body", "tampered-body"],
)
def test_signature_verification_snapshot(
    body: bytes,
    secret: str,
    signature_hex: str,
    expected_valid: bool,
) -> None:
    """Parametrized snapshot locking the HMAC verification logic."""
    server = WebhookServer(webhook_secret=secret)
    assert server.verify_signature(body, f"sha256={signature_hex}") is expected_valid


@pytest.mark.parametrize(
    "event_type,payload,expected_applicable",
    [
        ("pull_request", {"action": "opened"}, True),
        ("pull_request", {"action": "synchronize"}, True),
        ("pull_request", {"action": "reopened"}, True),
        ("pull_request", {"action": "closed"}, False),
        ("pull_request", {"action": "edited"}, False),
        (
            "issue_comment",
            {"action": "created", "issue": {"pull_request": {"url": "x"}}},
            True,
        ),
        (
            "issue_comment",
            {"action": "created", "issue": {}},
            False,
        ),
        (
            "issue_comment",
            {"action": "deleted", "issue": {"pull_request": {"url": "x"}}},
            False,
        ),
        ("push", {"ref": "refs/heads/main"}, False),
        ("ping", {}, False),
    ],
    ids=[
        "pr-opened",
        "pr-synchronize",
        "pr-reopened",
        "pr-closed",
        "pr-edited",
        "comment-on-pr",
        "comment-on-issue",
        "comment-deleted",
        "push",
        "ping",
    ],
)
def test_event_filtering_snapshot(
    event_type: str,
    payload: dict[str, Any],
    expected_applicable: bool,
) -> None:
    """Parametrized snapshot locking the event filtering logic."""
    server = _make_server()
    assert server.is_applicable_event(event_type, payload) is expected_applicable


# ---------------------------------------------------------------------------
# API shape tests
# ---------------------------------------------------------------------------


def test_webhook_request_shape() -> None:
    """Verify X-Hub-Signature-256, X-GitHub-Event, and Content-Type are consumed."""
    client = _make_client()
    payload = _pr_payload("opened")
    body = json.dumps(payload).encode()
    sig = _sign(body)

    # All expected headers present → success
    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 202


def test_webhook_response_shape_accepted() -> None:
    """202 response body is exactly {"status": "accepted"}."""
    client = _make_client()
    body = json.dumps(_pr_payload("opened")).encode()
    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted"}


def test_webhook_response_shape_forbidden() -> None:
    """403 response body is exactly {"status": "forbidden"}."""
    client = _make_client()
    body = json.dumps(_pr_payload("opened")).encode()
    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": "sha256=wrong",
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 403
    assert resp.json() == {"status": "forbidden"}


def test_webhook_response_shape_ignored() -> None:
    """200 response body is exactly {"status": "ignored"}."""
    client = _make_client()
    body = json.dumps({"action": "closed", "pull_request": {"number": 1}}).encode()
    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored"}
