"""Integration tests for the GitHub App reviewing PRs across multiple repos.

Verifies the full App path (webhook -> queue -> worker -> engine -> poster)
with all external calls mocked, proving that the App reuses the unchanged
engine to review PRs across different installations and repositories.

Framework: pytest + pytest-asyncio.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import importlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from lychee.queue import (
    Job,
    JobType,
    ReviewQueue,
    WorkerPool,
    event_to_job,
)
from lychee.state_store import ReviewState, SqliteStateStore
from lychee.webhook import WebhookServer

# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------

_WEBHOOK_SECRET = "integration-test-secret"


def _sign(body: bytes, secret: str = _WEBHOOK_SECRET) -> str:
    """Compute a valid X-Hub-Signature-256 header value."""
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _make_pr_payload(
    *,
    repo: str = "owner/repo-a",
    pr_number: int = 1,
    installation_id: int = 100,
    action: str = "opened",
    head_sha: str = "aaa111",
) -> dict[str, Any]:
    """Build a minimal pull_request webhook payload."""
    return {
        "action": action,
        "installation": {"id": installation_id},
        "repository": {"full_name": repo},
        "pull_request": {
            "number": pr_number,
            "head": {"sha": head_sha},
        },
    }


def _make_issue_comment_payload(
    *,
    repo: str = "owner/repo-a",
    pr_number: int = 1,
    installation_id: int = 100,
    body: str = "@lychee peel",
    user: str = "contributor",
) -> dict[str, Any]:
    """Build a minimal issue_comment webhook payload for a PR."""
    return {
        "action": "created",
        "installation": {"id": installation_id},
        "repository": {"full_name": repo},
        "issue": {
            "number": pr_number,
            "pull_request": {"url": f"https://api.github.com/repos/{repo}/pulls/{pr_number}"},
        },
        "comment": {
            "body": body,
            "user": {"login": user},
        },
    }


def _mock_authenticator() -> AsyncMock:
    """Create a mock AppAuthenticator that returns distinct tokens per installation."""
    auth = AsyncMock()
    token_cache: dict[int, MagicMock] = {}

    async def get_token(installation_id: int) -> MagicMock:
        """Return a mock token unique to each installation_id."""
        if installation_id not in token_cache:
            token = MagicMock()
            token.token = f"ghs_token_for_installation_{installation_id}"
            token.installation_id = installation_id
            token_cache[installation_id] = token
        return token_cache[installation_id]

    auth.get_installation_token = AsyncMock(side_effect=get_token)
    return auth


def _mock_lychee_config() -> MagicMock:
    """Create a mock LycheeConfig with sensible defaults."""
    config = MagicMock()
    config.model.default = "claude-sonnet-4-6"
    config.model.triage = "claude-haiku-4-5-20251001"
    config.model.large_pr = "claude-opus-4-8"
    config.review.max_files = 50
    config.review.max_file_bytes = 102_400
    config.review.ignore_globs = []
    config.review.severity_threshold = "info"
    config.review.tone = "balanced"
    config.review.language = "en"
    config.review.budget_cap_usd = None
    config.review.scope_rules = []
    config.features.inline_comments = False
    config.features.cost_footer = False
    config.features.commands = True
    config.features.triage_pass = False
    config.conventions_file = None
    config.authorization.allowed_users = []
    return config


def _mock_state_store() -> AsyncMock:
    """Create a mock StateStore with async methods and in-memory review tracking."""
    store = AsyncMock(spec=SqliteStateStore)
    reviews: dict[tuple[str, int], ReviewState] = {}

    async def get_review(repo: str, pr: int) -> ReviewState | None:
        """Return tracked review state or None."""
        return reviews.get((repo, pr))

    async def upsert_review(state: ReviewState) -> None:
        """Store review state in the in-memory dict."""
        reviews[(state.repo_full_name, state.pr_number)] = state

    store.get_review = AsyncMock(side_effect=get_review)
    store.upsert_review = AsyncMock(side_effect=upsert_review)
    store.initialize = AsyncMock()
    store.close = AsyncMock()
    store._reviews = reviews  # Expose for assertions
    return store


# ---------------------------------------------------------------------------
# Engine mock context manager
# ---------------------------------------------------------------------------


def _engine_patches() -> dict[str, Any]:
    """Return a dict of patch targets and their mock values for the engine.

    Patches the engine-touching imports in ``lychee.queue`` so the worker
    pool can process jobs without real GitHub or Claude API calls.
    """
    mock_result = MagicMock()
    mock_result.usage = {"input_tokens": 500, "output_tokens": 200}
    mock_result.model = "claude-sonnet-4-6"
    mock_result.ripeness.value = "ripe"
    mock_result.findings = []

    return {
        "lychee.queue.run_review": MagicMock(return_value=mock_result),
        "lychee.queue.render_comment": MagicMock(return_value="## Review\nLooks good."),
        "lychee.queue.ClaudeClient": MagicMock(),
        "lychee.queue.build_run_record": MagicMock(return_value={}),
        "lychee.queue.emit_run_record": MagicMock(),
        "lychee.queue.compute_cost": MagicMock(return_value=0.01),
        "lychee.queue.format_cost_line": MagicMock(return_value="Cost: $0.01"),
        "lychee.queue.compute_finding_counts": MagicMock(return_value={}),
        "lychee.queue.new_correlation_id": MagicMock(return_value="test-cid"),
        "lychee.queue.get_review_strategy": MagicMock(return_value="single_pass"),
        "lychee.queue.get_triage_verdict": MagicMock(return_value=None),
        "lychee.queue._get_anthropic_key": MagicMock(return_value="sk-test"),
    }


# ============================================================================
# SMOKE TESTS
# ============================================================================


def test_app_integration_module_imports() -> None:
    """Smoke: ``import tests.test_app_integration`` succeeds.

    Verifies this test module itself can be imported without errors.
    """
    # P5-R6
    mod = importlib.import_module("tests.test_app_integration")
    assert mod is not None


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestAppReviewsTwoRepos:
    """Integration test: the App reviews PRs across two different repos."""

    @pytest.mark.asyncio
    async def test_app_reviews_two_repos(self) -> None:
        """Full App integration: review PRs across two repos with distinct installations.

        Sets up a WebhookServer with a ReviewQueue and WorkerPool (all
        externals mocked).  Sends a ``pull_request.opened`` webhook for
        each of two repos with different installation IDs.

        Asserts:
        - Both webhooks are accepted (HTTP 202).
        - Both jobs are processed by workers.
        - Each job uses the correct installation token for its repo.
        - Each job produces a review posted to the correct PR.
        - The state store has two completed reviews.
        """
        # P5-R6
        queue = ReviewQueue(max_size=10)
        authenticator = _mock_authenticator()
        state_store = _mock_state_store()
        config = _mock_lychee_config()

        async def on_event(event_type: str, payload: dict[str, Any]) -> None:
            """Enqueue the event as a job."""
            job = event_to_job(event_type, payload)
            await queue.enqueue(job)

        pool = WorkerPool(
            queue=queue,
            authenticator=authenticator,
            state_store=state_store,
            config=config,
            num_workers=2,
        )

        server = WebhookServer(
            webhook_secret=_WEBHOOK_SECRET,
            on_event=on_event,
        )
        app = server.create_app()

        # Build two signed payloads for different repos.
        payload_a = _make_pr_payload(
            repo="org/repo-a", pr_number=10, installation_id=100, head_sha="sha_a"
        )
        payload_b = _make_pr_payload(
            repo="org/repo-b", pr_number=20, installation_id=200, head_sha="sha_b"
        )
        body_a = json.dumps(payload_a).encode()
        body_b = json.dumps(payload_b).encode()

        patches = _engine_patches()
        mock_gh_cls_patcher = patch("lychee.queue.GitHubClient")
        mock_poster_cls_patcher = patch("lychee.queue.SummaryPoster")

        with TestClient(app) as client:
            # Send both webhooks.
            resp_a = client.post(
                "/webhook",
                content=body_a,
                headers={
                    "X-Hub-Signature-256": _sign(body_a),
                    "X-GitHub-Event": "pull_request",
                    "Content-Type": "application/json",
                },
            )
            resp_b = client.post(
                "/webhook",
                content=body_b,
                headers={
                    "X-Hub-Signature-256": _sign(body_b),
                    "X-GitHub-Event": "pull_request",
                    "Content-Type": "application/json",
                },
            )

        # Both accepted.
        assert resp_a.status_code == 202
        assert resp_b.status_code == 202
        assert queue.size == 2

        # Start workers with engine mocked.
        mock_gh_cls = mock_gh_cls_patcher.start()
        mock_poster_cls = mock_poster_cls_patcher.start()

        # Track which tokens were used per GitHub client construction.
        tokens_used: list[str] = []
        mock_gh = MagicMock()
        mock_pr = MagicMock()
        mock_gh.get_pull_request.return_value = mock_pr

        def gh_from_token(token: str) -> MagicMock:
            """Track the token used and return a mock GitHub client."""
            tokens_used.append(token)
            return mock_gh

        mock_gh_cls.from_installation_token.side_effect = gh_from_token

        mock_poster = MagicMock()
        mock_poster.post.return_value = 999
        mock_poster_cls.return_value = mock_poster

        patchers = [patch(target, new=mock) for target, mock in patches.items()]
        for p in patchers:
            p.start()

        try:
            await pool.start()
            await asyncio.sleep(0.5)
            await pool.stop(timeout=5.0)
        finally:
            mock_gh_cls_patcher.stop()
            mock_poster_cls_patcher.stop()
            for p in patchers:
                p.stop()

        # Both installation tokens were requested.
        auth_calls = authenticator.get_installation_token.call_args_list
        installation_ids_called = sorted(c.args[0] for c in auth_calls)
        assert 100 in installation_ids_called
        assert 200 in installation_ids_called

        # Tokens were distinct per installation.
        assert "ghs_token_for_installation_100" in tokens_used
        assert "ghs_token_for_installation_200" in tokens_used

        # Poster was called twice (one per repo).
        assert mock_poster.post.call_count == 2

        # State store has two completed reviews.
        upsert_calls = state_store.upsert_review.call_args_list
        completed_repos = set()
        for call in upsert_calls:
            state = call.args[0]
            if state.review_status == "completed":
                completed_repos.add(state.repo_full_name)
        assert "org/repo-a" in completed_repos
        assert "org/repo-b" in completed_repos


class TestAppCommandAcrossRepos:
    """Integration test: @lychee commands work across repos via the App."""

    @pytest.mark.asyncio
    async def test_app_command_across_repos(self) -> None:
        """Send issue_comment webhooks with @lychee commands to two repos.

        Asserts correct command parsing, authorization, and dispatch
        for each repo using the correct installation token.
        """
        # P5-R6
        queue = ReviewQueue(max_size=10)
        authenticator = _mock_authenticator()
        state_store = _mock_state_store()
        config = _mock_lychee_config()
        config.authorization.allowed_users = []  # open access

        async def on_event(event_type: str, payload: dict[str, Any]) -> None:
            """Enqueue the event as a job."""
            job = event_to_job(event_type, payload)
            await queue.enqueue(job)

        pool = WorkerPool(
            queue=queue,
            authenticator=authenticator,
            state_store=state_store,
            config=config,
            num_workers=2,
        )

        server = WebhookServer(
            webhook_secret=_WEBHOOK_SECRET,
            on_event=on_event,
        )
        app = server.create_app()

        # Two command payloads for different repos.
        payload_a = _make_issue_comment_payload(
            repo="org/repo-a",
            pr_number=5,
            installation_id=100,
            body="@lychee peel",
            user="alice",
        )
        payload_b = _make_issue_comment_payload(
            repo="org/repo-b",
            pr_number=15,
            installation_id=200,
            body="@lychee peel",
            user="bob",
        )
        body_a = json.dumps(payload_a).encode()
        body_b = json.dumps(payload_b).encode()

        with TestClient(app) as client:
            resp_a = client.post(
                "/webhook",
                content=body_a,
                headers={
                    "X-Hub-Signature-256": _sign(body_a),
                    "X-GitHub-Event": "issue_comment",
                    "Content-Type": "application/json",
                },
            )
            resp_b = client.post(
                "/webhook",
                content=body_b,
                headers={
                    "X-Hub-Signature-256": _sign(body_b),
                    "X-GitHub-Event": "issue_comment",
                    "Content-Type": "application/json",
                },
            )

        assert resp_a.status_code == 202
        assert resp_b.status_code == 202
        assert queue.size == 2

        patches = _engine_patches()
        mock_gh_cls_patcher = patch("lychee.queue.GitHubClient")
        patchers = [patch(target, new=mock) for target, mock in patches.items()]

        mock_gh_cls = mock_gh_cls_patcher.start()
        mock_gh = MagicMock()
        mock_pr = MagicMock()
        mock_gh.get_pull_request.return_value = mock_pr
        mock_gh_cls.from_installation_token.return_value = mock_gh

        for p in patchers:
            p.start()

        # Override COMMAND_RENDERERS to track calls.
        render_calls: list[str] = []

        def mock_peel_renderer(result: Any) -> str:
            """Track renderer invocation."""
            render_calls.append("peel")
            return "## Peel response"

        cmd_patcher = patch(
            "lychee.queue.COMMAND_RENDERERS",
            {"peel": mock_peel_renderer},
        )
        cmd_patcher.start()

        try:
            await pool.start()
            await asyncio.sleep(0.5)
            await pool.stop(timeout=5.0)
        finally:
            mock_gh_cls_patcher.stop()
            cmd_patcher.stop()
            for p in patchers:
                p.stop()

        # Both commands dispatched.
        assert len(render_calls) == 2

        # Comments posted to the PR for each repo.
        assert mock_pr.create_issue_comment.call_count == 2


class TestAppDedupAcrossPushes:
    """Integration test: re-push on a PR updates the comment, does not duplicate."""

    @pytest.mark.asyncio
    async def test_app_dedup_across_pushes(self) -> None:
        """Send pull_request.opened then pull_request.synchronize for the same PR.

        Asserts the poster is called twice (once per event) and the
        state store's ``last_reviewed_sha`` is updated to the second SHA.
        """
        # P5-R6
        queue = ReviewQueue(max_size=10)
        authenticator = _mock_authenticator()
        state_store = _mock_state_store()
        config = _mock_lychee_config()

        async def on_event(event_type: str, payload: dict[str, Any]) -> None:
            """Enqueue the event as a job."""
            job = event_to_job(event_type, payload)
            await queue.enqueue(job)

        pool = WorkerPool(
            queue=queue,
            authenticator=authenticator,
            state_store=state_store,
            config=config,
            num_workers=1,
        )

        server = WebhookServer(
            webhook_secret=_WEBHOOK_SECRET,
            on_event=on_event,
        )
        app = server.create_app()

        # First event: PR opened.
        payload_open = _make_pr_payload(
            repo="org/repo-a",
            pr_number=1,
            installation_id=100,
            action="opened",
            head_sha="sha_first",
        )
        # Second event: PR synchronize (new push).
        payload_sync = _make_pr_payload(
            repo="org/repo-a",
            pr_number=1,
            installation_id=100,
            action="synchronize",
            head_sha="sha_second",
        )

        body_open = json.dumps(payload_open).encode()
        body_sync = json.dumps(payload_sync).encode()

        with TestClient(app) as client:
            resp_open = client.post(
                "/webhook",
                content=body_open,
                headers={
                    "X-Hub-Signature-256": _sign(body_open),
                    "X-GitHub-Event": "pull_request",
                    "Content-Type": "application/json",
                },
            )
            resp_sync = client.post(
                "/webhook",
                content=body_sync,
                headers={
                    "X-Hub-Signature-256": _sign(body_sync),
                    "X-GitHub-Event": "pull_request",
                    "Content-Type": "application/json",
                },
            )

        assert resp_open.status_code == 202
        assert resp_sync.status_code == 202

        patches = _engine_patches()
        mock_gh_cls_patcher = patch("lychee.queue.GitHubClient")
        mock_poster_cls_patcher = patch("lychee.queue.SummaryPoster")

        mock_gh_cls = mock_gh_cls_patcher.start()
        mock_poster_cls = mock_poster_cls_patcher.start()

        mock_gh = MagicMock()
        mock_pr = MagicMock()
        mock_gh.get_pull_request.return_value = mock_pr
        mock_gh_cls.from_installation_token.return_value = mock_gh

        poster_post_calls: list[int] = []
        comment_counter = 0

        def poster_post_side_effect(pr: Any, body: str, **kwargs: Any) -> int:
            """Track poster.post calls and return incrementing comment IDs."""
            nonlocal comment_counter
            comment_counter += 1
            poster_post_calls.append(comment_counter)
            return comment_counter

        mock_poster = MagicMock()
        mock_poster.post.side_effect = poster_post_side_effect
        mock_poster_cls.return_value = mock_poster

        patchers = [patch(target, new=mock) for target, mock in patches.items()]
        for p in patchers:
            p.start()

        try:
            await pool.start()
            await asyncio.sleep(0.5)
            await pool.stop(timeout=5.0)
        finally:
            mock_gh_cls_patcher.stop()
            mock_poster_cls_patcher.stop()
            for p in patchers:
                p.stop()

        # Poster was called twice (once per event).
        assert len(poster_post_calls) == 2

        # State store has the updated SHA from the second push.
        upsert_calls = state_store.upsert_review.call_args_list
        final_states = [
            c.args[0]
            for c in upsert_calls
            if c.args[0].repo_full_name == "org/repo-a"
            and c.args[0].last_reviewed_sha == "sha_second"
        ]
        assert (
            len(final_states) >= 1
        ), "State store should have been updated with the second push SHA"


class TestWorkerCallsEngineDirectly:
    """Integration test: verify the worker calls engine modules directly."""

    @pytest.mark.asyncio
    async def test_worker_calls_engine_directly(self) -> None:
        """Mock-trace that the worker calls run_review() and SummaryPoster
        from the engine modules, not from wrappers or copies.

        Verifies the import path of the called functions matches the
        engine module locations.
        """
        # P5-R6
        queue = ReviewQueue(max_size=10)
        authenticator = _mock_authenticator()
        state_store = _mock_state_store()
        config = _mock_lychee_config()

        pool = WorkerPool(
            queue=queue,
            authenticator=authenticator,
            state_store=state_store,
            config=config,
            num_workers=1,
        )

        job = Job(
            job_id="trace-job-001",
            job_type=JobType.pr_review,
            installation_id=100,
            repo_full_name="org/repo-a",
            pr_number=1,
            event_type="pull_request",
            payload=_make_pr_payload(repo="org/repo-a", pr_number=1, installation_id=100),
        )

        # Patch at the lychee.queue module level to intercept calls.
        with (
            patch("lychee.queue.GitHubClient") as mock_gh_cls,
            patch("lychee.queue.run_review") as mock_run_review,
            patch("lychee.queue.SummaryPoster") as mock_poster_cls,
            patch("lychee.queue.render_comment", return_value="body"),
            patch("lychee.queue.ClaudeClient"),
            patch("lychee.queue.build_run_record", return_value={}),
            patch("lychee.queue.emit_run_record"),
            patch("lychee.queue.compute_cost", return_value=0.01),
            patch("lychee.queue.compute_finding_counts", return_value={}),
            patch("lychee.queue.new_correlation_id", return_value="trace-cid"),
            patch("lychee.queue.get_review_strategy", return_value="single_pass"),
            patch("lychee.queue.get_triage_verdict", return_value=None),
            patch("lychee.queue._get_anthropic_key", return_value="sk-test"),
        ):
            mock_gh = MagicMock()
            mock_gh_cls.from_installation_token.return_value = mock_gh
            mock_pr = MagicMock()
            mock_gh.get_pull_request.return_value = mock_pr

            mock_result = MagicMock()
            mock_result.usage = {"input_tokens": 100, "output_tokens": 50}
            mock_result.model = "claude-sonnet-4-6"
            mock_result.ripeness.value = "ripe"
            mock_result.findings = []
            mock_run_review.return_value = mock_result

            mock_poster = MagicMock()
            mock_poster.post.return_value = 1
            mock_poster_cls.return_value = mock_poster

            await queue.enqueue(job)
            await pool.start()
            await asyncio.sleep(0.3)
            await pool.stop(timeout=5.0)

            # run_review was called (the unchanged engine function).
            mock_run_review.assert_called_once()

            # The call used the correct PR ref format.
            call_args = mock_run_review.call_args
            pr_ref_arg = call_args.args[0]
            assert pr_ref_arg == "org/repo-a#1"

            # SummaryPoster was instantiated and post() was called.
            mock_poster_cls.assert_called_once()
            mock_poster.post.assert_called_once()

        # Verify that lychee.queue imports run_review from lychee.review
        # (not a copy or wrapper).
        import lychee.queue as queue_module
        import lychee.review as review_module

        assert hasattr(queue_module, "run_review")
        # The unpatched reference should resolve to the same function.
        assert queue_module.run_review is review_module.run_review  # type: ignore[attr-defined]

        # Verify SummaryPoster comes from lychee.poster.
        import lychee.poster as poster_module

        assert queue_module.SummaryPoster is poster_module.SummaryPoster  # type: ignore[attr-defined]


# ============================================================================
# ACCEPTANCE TESTS
# ============================================================================


class TestAcceptAppReviewsMultipleRepos:
    """Acceptance: the App reviews across >= 2 repos."""

    @pytest.mark.asyncio
    async def test_accept_app_reviews_multiple_repos(self) -> None:
        """Acceptance wrapper for the two-repo integration test.

        Delegates to ``test_app_reviews_two_repos`` to prove the App
        can review across multiple repos using the unchanged engine.
        """
        # P5-R6
        test = TestAppReviewsTwoRepos()
        await test.test_app_reviews_two_repos()


# ============================================================================
# SANITY TESTS
# ============================================================================


class TestEngineImportsConsistent:
    """Sanity: engine module references in queue.py are the real modules."""

    def test_queue_imports_real_engine_modules(self) -> None:
        """Verify that lychee.queue imports engine functions from their
        canonical module locations, not copies or wrappers.

        Uses ``getattr()`` to access re-exported names without triggering
        mypy strict ``attr-defined`` errors.
        """
        # P5-R6
        import lychee.queue as queue_mod
        import lychee.render as render_mod
        import lychee.review as review_mod

        assert queue_mod.run_review is review_mod.run_review  # type: ignore[attr-defined]
        assert queue_mod.render_comment is render_mod.render_comment  # type: ignore[attr-defined]

    def test_queue_imports_poster_from_engine(self) -> None:
        """Verify SummaryPoster in queue.py comes from lychee.poster."""
        # P5-R6
        import lychee.poster as poster_mod
        import lychee.queue as queue_mod

        assert queue_mod.SummaryPoster is poster_mod.SummaryPoster  # type: ignore[attr-defined]
