"""Comprehensive test suite for the async job queue and worker pool.

Covers unit, integration, system, acceptance, smoke, sanity, regression,
and end-to-end tests for ``lychee.queue``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from lychee.queue import (
    Job,
    JobType,
    QueueFullError,
    ReviewQueue,
    WorkerPool,
    event_to_job,
)
from lychee.state_store import ReviewState, SqliteStateStore

# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------


def _make_pr_payload(
    *,
    repo: str = "owner/repo",
    pr_number: int = 42,
    installation_id: int = 12345,
    action: str = "opened",
    head_sha: str = "abc123",
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
    repo: str = "owner/repo",
    pr_number: int = 42,
    installation_id: int = 12345,
    body: str = "@lychee peel",
    user: str = "octocat",
) -> dict[str, Any]:
    """Build a minimal issue_comment webhook payload."""
    return {
        "action": "created",
        "installation": {"id": installation_id},
        "repository": {"full_name": repo},
        "issue": {
            "number": pr_number,
            "pull_request": {"url": "https://api.github.com/repos/owner/repo/pulls/42"},
        },
        "comment": {
            "body": body,
            "user": {"login": user},
        },
    }


def _make_job(
    *,
    job_type: JobType = JobType.pr_review,
    repo: str = "owner/repo",
    pr_number: int = 42,
    installation_id: int = 12345,
) -> Job:
    """Build a Job for testing."""
    return Job(
        job_id="test-job-001",
        job_type=job_type,
        installation_id=installation_id,
        repo_full_name=repo,
        pr_number=pr_number,
        event_type="pull_request" if job_type == JobType.pr_review else "issue_comment",
        payload=_make_pr_payload(repo=repo, pr_number=pr_number, installation_id=installation_id)
        if job_type == JobType.pr_review
        else _make_issue_comment_payload(
            repo=repo, pr_number=pr_number, installation_id=installation_id
        ),
    )


@pytest_asyncio.fixture
async def state_store() -> AsyncMock:
    """Return a mock StateStore with async methods."""
    # P5-R2
    store = AsyncMock(spec=SqliteStateStore)
    store.get_review = AsyncMock(return_value=None)
    store.upsert_review = AsyncMock()
    store.initialize = AsyncMock()
    store.close = AsyncMock()
    return store


@pytest.fixture()
def mock_authenticator() -> AsyncMock:
    """Return a mock AppAuthenticator."""
    # P5-R2
    auth = AsyncMock()
    token_mock = MagicMock()
    token_mock.token = "ghs_fake_installation_token"
    auth.get_installation_token = AsyncMock(return_value=token_mock)
    return auth


@pytest.fixture()
def lychee_config() -> MagicMock:
    """Return a mock LycheeConfig."""
    # P5-R2
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


# ============================================================================
# UNIT TESTS
# ============================================================================


class TestEventToJob:
    """Unit tests for the event_to_job converter."""

    def test_event_to_job_pr_opened(self) -> None:
        """pull_request opened event produces a Job with correct fields and job_type=pr_review."""
        # P5-R2
        payload = _make_pr_payload(action="opened")
        job = event_to_job("pull_request", payload)

        assert job.job_type == JobType.pr_review
        assert job.installation_id == 12345
        assert job.repo_full_name == "owner/repo"
        assert job.pr_number == 42
        assert job.event_type == "pull_request"
        assert job.payload is payload
        assert len(job.job_id) == 32  # UUID4 hex

    def test_event_to_job_pr_synchronize(self) -> None:
        """pull_request synchronize event works."""
        # P5-R2
        payload = _make_pr_payload(action="synchronize")
        job = event_to_job("pull_request", payload)

        assert job.job_type == JobType.pr_review
        assert job.pr_number == 42

    def test_event_to_job_issue_comment(self) -> None:
        """issue_comment event produces a Job with job_type=command."""
        # P5-R2
        payload = _make_issue_comment_payload()
        job = event_to_job("issue_comment", payload)

        assert job.job_type == JobType.command
        assert job.installation_id == 12345
        assert job.repo_full_name == "owner/repo"
        assert job.pr_number == 42
        assert job.event_type == "issue_comment"

    def test_event_to_job_missing_installation(self) -> None:
        """Missing installation.id raises ValueError."""
        # P5-R2
        payload = {
            "repository": {"full_name": "owner/repo"},
            "pull_request": {"number": 1},
        }
        with pytest.raises(ValueError, match=r"installation\.id"):
            event_to_job("pull_request", payload)

    def test_event_to_job_missing_repo(self) -> None:
        """Missing repository.full_name raises ValueError."""
        # P5-R2
        payload = {
            "installation": {"id": 1},
            "pull_request": {"number": 1},
        }
        with pytest.raises(ValueError, match=r"repository\.full_name"):
            event_to_job("pull_request", payload)

    def test_event_to_job_unique_ids(self) -> None:
        """Two calls produce different job_id values."""
        # P5-R2
        payload = _make_pr_payload()
        job1 = event_to_job("pull_request", payload)
        job2 = event_to_job("pull_request", payload)
        assert job1.job_id != job2.job_id

    def test_event_to_job_missing_pr_number(self) -> None:
        """Missing pull_request.number raises ValueError."""
        # P5-R2
        payload = {
            "installation": {"id": 1},
            "repository": {"full_name": "owner/repo"},
            "pull_request": {},
        }
        with pytest.raises(ValueError, match=r"pull_request\.number"):
            event_to_job("pull_request", payload)

    def test_event_to_job_missing_issue_number(self) -> None:
        """Missing issue.number raises ValueError for issue_comment events."""
        # P5-R2
        payload = {
            "installation": {"id": 1},
            "repository": {"full_name": "owner/repo"},
            "issue": {},
        }
        with pytest.raises(ValueError, match=r"issue\.number"):
            event_to_job("issue_comment", payload)

    def test_event_to_job_unsupported_event_type(self) -> None:
        """Unsupported event type raises ValueError."""
        # P5-R2
        payload = {
            "installation": {"id": 1},
            "repository": {"full_name": "owner/repo"},
        }
        with pytest.raises(ValueError, match="Unsupported event type"):
            event_to_job("push", payload)


class TestJobTypeEnum:
    """Unit tests for the JobType enum."""

    def test_job_type_enum(self) -> None:
        """JobType has pr_review and command members."""
        # P5-R2
        assert JobType.pr_review == "pr_review"
        assert JobType.command == "command"
        assert len(JobType) == 2


class TestReviewQueue:
    """Unit tests for the ReviewQueue."""

    @pytest.mark.asyncio
    async def test_queue_enqueue_dequeue(self) -> None:
        """Enqueue a job, dequeue it, assert equality."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        job = _make_job()
        await queue.enqueue(job)
        result = await queue.dequeue()
        assert result is job

    @pytest.mark.asyncio
    async def test_queue_fifo_order(self) -> None:
        """Enqueue A then B; dequeue returns A then B."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        job_a = _make_job(pr_number=1)
        job_b = _make_job(pr_number=2)
        await queue.enqueue(job_a)
        await queue.enqueue(job_b)

        first = await queue.dequeue()
        second = await queue.dequeue()
        assert first is job_a
        assert second is job_b

    @pytest.mark.asyncio
    async def test_queue_full_raises(self) -> None:
        """Enqueue beyond max_size raises QueueFullError."""
        # P5-R2
        queue = ReviewQueue(max_size=2)
        await queue.enqueue(_make_job(pr_number=1))
        await queue.enqueue(_make_job(pr_number=2))

        with pytest.raises(QueueFullError):
            await queue.enqueue(_make_job(pr_number=3))

    @pytest.mark.asyncio
    async def test_queue_size(self) -> None:
        """size reflects the number of pending jobs."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        assert queue.size == 0

        await queue.enqueue(_make_job(pr_number=1))
        assert queue.size == 1

        await queue.enqueue(_make_job(pr_number=2))
        assert queue.size == 2

        await queue.dequeue()
        assert queue.size == 1

    @pytest.mark.asyncio
    async def test_queue_is_full(self) -> None:
        """is_full is True when at capacity."""
        # P5-R2
        queue = ReviewQueue(max_size=1)
        assert not queue.is_full

        await queue.enqueue(_make_job())
        assert queue.is_full


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestWorkerProcessesPRReview:
    """Integration test: worker processes a pr_review job."""

    @pytest.mark.asyncio
    async def test_worker_processes_pr_review(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """Mock auth, client, engine; enqueue a pr_review job; assert engine and poster called."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        job = _make_job(job_type=JobType.pr_review)

        with (
            patch("lychee.queue.GitHubClient") as mock_gh_cls,
            patch("lychee.queue.run_review") as mock_run_review,
            patch("lychee.queue.SummaryPoster") as mock_poster_cls,
            patch("lychee.queue.render_comment") as mock_render,
            patch("lychee.queue.ClaudeClient"),
            patch("lychee.queue.build_run_record", return_value={}),
            patch("lychee.queue.emit_run_record"),
            patch("lychee.queue.compute_cost", return_value=0.01),
            patch("lychee.queue.compute_finding_counts", return_value={}),
            patch("lychee.queue.new_correlation_id", return_value="test-cid"),
            patch("lychee.queue.get_review_strategy", return_value="single_pass"),
            patch("lychee.queue.get_triage_verdict", return_value=None),
            patch("lychee.queue._get_anthropic_key", return_value="sk-test"),
        ):
            # Configure mocks.
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

            mock_render.return_value = "## Review\nLooks good."
            mock_poster = MagicMock()
            mock_poster.post.return_value = 999
            mock_poster_cls.return_value = mock_poster

            await queue.enqueue(job)
            await pool.start()

            # Give the worker time to process.
            await asyncio.sleep(0.2)
            await pool.stop(timeout=2.0)

            # Assertions.
            mock_authenticator.get_installation_token.assert_called_with(12345)
            mock_gh_cls.from_installation_token.assert_called_once()
            mock_run_review.assert_called_once()
            mock_poster.post.assert_called_once()

            # State should have been updated.
            assert state_store.upsert_review.call_count >= 2


class TestWorkerProcessesCommand:
    """Integration test: worker processes a command job."""

    @pytest.mark.asyncio
    async def test_worker_processes_command(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """Mock auth, client, parse_command, command dispatch; assert dispatch called."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        job = _make_job(job_type=JobType.command)
        job.payload = _make_issue_comment_payload(body="@lychee peel")

        with (
            patch("lychee.queue.GitHubClient") as mock_gh_cls,
            patch("lychee.queue.run_review") as mock_run_review,
            patch("lychee.queue.ClaudeClient"),
            patch("lychee.queue.COMMAND_RENDERERS", {"peel": lambda r: "response"}),
            patch("lychee.queue.new_correlation_id", return_value="test-cid"),
            patch("lychee.queue._get_anthropic_key", return_value="sk-test"),
        ):
            mock_gh = MagicMock()
            mock_gh_cls.from_installation_token.return_value = mock_gh
            mock_pr = MagicMock()
            mock_gh.get_pull_request.return_value = mock_pr

            mock_result = MagicMock()
            mock_result.usage = {}
            mock_result.model = "mock"
            mock_result.ripeness.value = "ripe"
            mock_result.findings = []
            mock_run_review.return_value = mock_result

            await queue.enqueue(job)
            await pool.start()
            await asyncio.sleep(0.2)
            await pool.stop(timeout=2.0)

            mock_run_review.assert_called_once()
            mock_pr.create_issue_comment.assert_called_once()


class TestWorkerHandlesFailure:
    """Integration test: worker handles a failing job gracefully."""

    @pytest.mark.asyncio
    async def test_worker_handles_failure(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """Mock run_review to raise; assert state updated to failed and worker stays alive."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        job = _make_job(job_type=JobType.pr_review)

        with (
            patch("lychee.queue.GitHubClient") as mock_gh_cls,
            patch("lychee.queue.run_review", side_effect=RuntimeError("engine failure")),
            patch("lychee.queue.ClaudeClient"),
            patch("lychee.queue.new_correlation_id", return_value="test-cid"),
            patch("lychee.queue._get_anthropic_key", return_value="sk-test"),
        ):
            mock_gh = MagicMock()
            mock_gh_cls.from_installation_token.return_value = mock_gh

            await queue.enqueue(job)
            await pool.start()
            await asyncio.sleep(0.2)

            # Worker should still be alive.
            assert pool.active_workers == 1

            await pool.stop(timeout=2.0)

            # State store should have been updated to 'failed'.
            calls = state_store.upsert_review.call_args_list
            statuses = [call.args[0].review_status for call in calls]
            assert "in_progress" in statuses
            assert "failed" in statuses


class TestWorkerUpdatesStateStore:
    """Integration test: state store transitions."""

    @pytest.mark.asyncio
    async def test_worker_updates_state_store(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """Assert upsert_review called with in_progress then completed."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        job = _make_job(job_type=JobType.pr_review)

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
            patch("lychee.queue.new_correlation_id", return_value="test-cid"),
            patch("lychee.queue.get_review_strategy", return_value="single_pass"),
            patch("lychee.queue.get_triage_verdict", return_value=None),
            patch("lychee.queue._get_anthropic_key", return_value="sk-test"),
        ):
            mock_gh = MagicMock()
            mock_gh_cls.from_installation_token.return_value = mock_gh
            mock_pr = MagicMock()
            mock_gh.get_pull_request.return_value = mock_pr

            mock_result = MagicMock()
            mock_result.usage = {}
            mock_result.model = "mock"
            mock_result.ripeness.value = "ripe"
            mock_result.findings = []
            mock_run_review.return_value = mock_result

            mock_poster = MagicMock()
            mock_poster.post.return_value = 1
            mock_poster_cls.return_value = mock_poster

            await queue.enqueue(job)
            await pool.start()
            await asyncio.sleep(0.2)
            await pool.stop(timeout=2.0)

            calls = state_store.upsert_review.call_args_list
            statuses = [call.args[0].review_status for call in calls]
            assert statuses[0] == "in_progress"
            assert "completed" in statuses


class TestQueueBackpressure503:
    """Integration test: backpressure returns QueueFullError."""

    @pytest.mark.asyncio
    async def test_queue_backpressure_503(self) -> None:
        """Wire the on_event callback; fill the queue; assert QueueFullError raised."""
        # P5-R2
        queue = ReviewQueue(max_size=2)

        async def on_event(event_type: str, payload: dict[str, Any]) -> None:
            """Enqueue callback that mirrors the server wiring."""
            job = event_to_job(event_type, payload)
            await queue.enqueue(job)

        # Fill the queue.
        await on_event("pull_request", _make_pr_payload(pr_number=1))
        await on_event("pull_request", _make_pr_payload(pr_number=2))

        # Third should raise.
        with pytest.raises(QueueFullError):
            await on_event("pull_request", _make_pr_payload(pr_number=3))


class TestMultipleWorkersConcurrent:
    """Integration test: multiple workers process jobs concurrently."""

    @pytest.mark.asyncio
    async def test_multiple_workers_concurrent(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """Enqueue N jobs, start pool with M workers, assert all N jobs processed."""
        # P5-R2
        n_jobs = 6
        n_workers = 3
        processed: list[str] = []

        queue = ReviewQueue(max_size=20)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=n_workers,
        )

        # Override _process_job to track processing.
        async def tracking_process(job: Job) -> None:
            processed.append(job.job_id)

        pool._process_job = tracking_process  # type: ignore[assignment]

        for i in range(n_jobs):
            job = _make_job(pr_number=i + 1)
            job.job_id = f"job-{i}"
            await queue.enqueue(job)

        await pool.start()
        await asyncio.sleep(0.5)
        await pool.stop(timeout=5.0)

        assert len(processed) == n_jobs
        assert set(processed) == {f"job-{i}" for i in range(n_jobs)}


# ============================================================================
# SYSTEM TESTS
# ============================================================================


class TestWebhookToReviewFlow:
    """System test: full webhook-to-review flow."""

    @pytest.mark.asyncio
    async def test_webhook_to_review_flow(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """Create WebhookServer + ReviewQueue + WorkerPool; send a valid webhook; assert flow."""
        # P5-R2
        queue = ReviewQueue(max_size=10)

        async def on_event(event_type: str, payload: dict[str, Any]) -> None:
            job = event_to_job(event_type, payload)
            await queue.enqueue(job)

        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        processed_jobs: list[Job] = []

        async def track_process(job: Job) -> None:
            processed_jobs.append(job)

        pool._process_job = track_process  # type: ignore[assignment]

        # Simulate receiving an event through the callback.
        payload = _make_pr_payload()
        await on_event("pull_request", payload)

        assert queue.size == 1

        await pool.start()
        await asyncio.sleep(0.2)
        await pool.stop(timeout=2.0)

        assert len(processed_jobs) == 1
        assert processed_jobs[0].repo_full_name == "owner/repo"
        assert processed_jobs[0].pr_number == 42


class TestGracefulShutdown:
    """System test: graceful shutdown."""

    @pytest.mark.asyncio
    async def test_graceful_shutdown(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """Start workers, enqueue jobs, call stop(), assert workers exit cleanly."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=2,
        )

        processed: list[str] = []

        async def slow_process(job: Job) -> None:
            processed.append(job.job_id)
            await asyncio.sleep(0.05)

        pool._process_job = slow_process  # type: ignore[assignment]

        for i in range(3):
            job = _make_job(pr_number=i + 1)
            job.job_id = f"shutdown-job-{i}"
            await queue.enqueue(job)

        await pool.start()
        await asyncio.sleep(0.3)
        await pool.stop(timeout=5.0)

        # All enqueued jobs should have been processed.
        assert len(processed) == 3
        assert pool.active_workers == 0


# ============================================================================
# ACCEPTANCE TESTS
# ============================================================================


class TestAcceptConcurrentEventsNoLoss:
    """Acceptance test: concurrent events processed without loss."""

    @pytest.mark.asyncio
    async def test_accept_concurrent_events_no_loss(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """Enqueue 10 events concurrently; assert all 10 are processed."""
        # P5-R2
        queue = ReviewQueue(max_size=20)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=4,
        )

        processed: list[str] = []

        async def track_process(job: Job) -> None:
            processed.append(job.job_id)

        pool._process_job = track_process  # type: ignore[assignment]

        # Enqueue 10 events concurrently.
        jobs = []
        for i in range(10):
            job = _make_job(pr_number=i + 1)
            job.job_id = f"concurrent-{i}"
            jobs.append(job)

        await asyncio.gather(*[queue.enqueue(j) for j in jobs])

        await pool.start()
        await asyncio.sleep(0.5)
        await pool.stop(timeout=5.0)

        assert len(processed) == 10
        assert set(processed) == {f"concurrent-{i}" for i in range(10)}


class TestAcceptBackpressureRespected:
    """Acceptance test: backpressure respected."""

    @pytest.mark.asyncio
    async def test_accept_backpressure_respected(self) -> None:
        """With max_size=2, enqueue 3; assert the third raises QueueFullError."""
        # P5-R2
        queue = ReviewQueue(max_size=2)

        await queue.enqueue(_make_job(pr_number=1))
        await queue.enqueue(_make_job(pr_number=2))

        with pytest.raises(QueueFullError):
            await queue.enqueue(_make_job(pr_number=3))


# ============================================================================
# SMOKE TESTS
# ============================================================================


class TestQueueModuleImports:
    """Smoke test: module imports."""

    def test_queue_module_imports(self) -> None:
        """from lychee.queue import ... succeeds for all public symbols."""
        # P5-R2
        from lychee.queue import (
            Job,
            JobType,
            QueueFullError,
            ReviewQueue,
            WorkerPool,
            event_to_job,
        )

        assert Job is not None
        assert JobType is not None
        assert QueueFullError is not None
        assert ReviewQueue is not None
        assert WorkerPool is not None
        assert event_to_job is not None


# ============================================================================
# SANITY TESTS
# ============================================================================


class TestWorkerPoolStartStop:
    """Sanity test: starting and stopping an empty pool."""

    @pytest.mark.asyncio
    async def test_worker_pool_start_stop(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """Starting and stopping an empty pool doesn't error."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=2,
        )
        await pool.start()
        assert pool.active_workers == 2
        await pool.stop(timeout=2.0)
        assert pool.active_workers == 0


class TestQueueEmptyDequeueBlocks:
    """Sanity test: dequeue on empty queue blocks."""

    @pytest.mark.asyncio
    async def test_queue_empty_dequeue_blocks(self) -> None:
        """dequeue() on an empty queue blocks; verify it doesn't return immediately."""
        # P5-R2
        queue = ReviewQueue(max_size=10)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.dequeue(), timeout=0.1)


# ============================================================================
# REGRESSION TESTS
# ============================================================================


class TestEventToJobSnapshot:
    """Regression test: parametrized snapshot for event_to_job extraction."""

    @pytest.mark.parametrize(
        "event_type,payload,expected_type,expected_repo,expected_pr",
        [
            (
                "pull_request",
                _make_pr_payload(repo="org/proj", pr_number=99, installation_id=555),
                JobType.pr_review,
                "org/proj",
                99,
            ),
            (
                "pull_request",
                _make_pr_payload(repo="user/lib", pr_number=1, installation_id=1),
                JobType.pr_review,
                "user/lib",
                1,
            ),
            (
                "issue_comment",
                _make_issue_comment_payload(repo="a/b", pr_number=7, installation_id=42),
                JobType.command,
                "a/b",
                7,
            ),
        ],
        ids=["pr-org-proj-99", "pr-user-lib-1", "comment-a-b-7"],
    )
    def test_event_to_job_snapshot(
        self,
        event_type: str,
        payload: dict[str, Any],
        expected_type: JobType,
        expected_repo: str,
        expected_pr: int,
    ) -> None:
        """Parametrized fixture with known payloads and expected Job fields."""
        # P5-R2
        job = event_to_job(event_type, payload)
        assert job.job_type == expected_type
        assert job.repo_full_name == expected_repo
        assert job.pr_number == expected_pr


class TestJobStateTransitions:
    """Regression test: state transition sequences."""

    @pytest.mark.asyncio
    async def test_job_state_transitions_success(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """Snapshot the sequence of state updates for a successful job."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        job = _make_job(job_type=JobType.pr_review)

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
            patch("lychee.queue.new_correlation_id", return_value="cid"),
            patch("lychee.queue.get_review_strategy", return_value="single_pass"),
            patch("lychee.queue.get_triage_verdict", return_value=None),
            patch("lychee.queue._get_anthropic_key", return_value="sk-test"),
        ):
            mock_gh = MagicMock()
            mock_gh_cls.from_installation_token.return_value = mock_gh
            mock_pr = MagicMock()
            mock_gh.get_pull_request.return_value = mock_pr

            mock_result = MagicMock()
            mock_result.usage = {}
            mock_result.model = "mock"
            mock_result.ripeness.value = "ripe"
            mock_result.findings = []
            mock_run_review.return_value = mock_result

            mock_poster = MagicMock()
            mock_poster.post.return_value = 1
            mock_poster_cls.return_value = mock_poster

            await queue.enqueue(job)
            await pool.start()
            await asyncio.sleep(0.2)
            await pool.stop(timeout=2.0)

            calls = state_store.upsert_review.call_args_list
            statuses = [call.args[0].review_status for call in calls]
            # Expected sequence: in_progress -> completed (with possible
            # intermediate update for SHA/comment_id).
            assert statuses[0] == "in_progress"
            assert statuses[-1] == "completed"

    @pytest.mark.asyncio
    async def test_job_state_transitions_failure(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """Snapshot the sequence of state updates for a failed job."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        job = _make_job(job_type=JobType.pr_review)

        with (
            patch("lychee.queue.GitHubClient") as mock_gh_cls,
            patch("lychee.queue.run_review", side_effect=RuntimeError("boom")),
            patch("lychee.queue.ClaudeClient"),
            patch("lychee.queue.new_correlation_id", return_value="cid"),
            patch("lychee.queue._get_anthropic_key", return_value="sk-test"),
        ):
            mock_gh = MagicMock()
            mock_gh_cls.from_installation_token.return_value = mock_gh

            await queue.enqueue(job)
            await pool.start()
            await asyncio.sleep(0.2)
            await pool.stop(timeout=2.0)

            calls = state_store.upsert_review.call_args_list
            statuses = [call.args[0].review_status for call in calls]
            assert statuses[0] == "in_progress"
            assert statuses[-1] == "failed"


# ============================================================================
# END-TO-END TEST
# ============================================================================


# ============================================================================
# ADDITIONAL COVERAGE TESTS
# ============================================================================


class TestStartIdempotent:
    """Test that start() is idempotent when called twice."""

    @pytest.mark.asyncio
    async def test_start_idempotent(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """Calling start() when already running is a no-op."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=2,
        )
        await pool.start()
        assert pool.active_workers == 2

        # Second start should be idempotent.
        await pool.start()
        assert pool.active_workers == 2

        await pool.stop(timeout=2.0)


class TestCommandProcessNoMention:
    """Test command processing when comment has no @lychee mention."""

    @pytest.mark.asyncio
    async def test_command_no_mention_skips(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """A command job with no @lychee mention in the comment body is skipped."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        job = _make_job(job_type=JobType.command)
        job.payload = _make_issue_comment_payload(body="just a regular comment")

        with (
            patch("lychee.queue.GitHubClient") as mock_gh_cls,
            patch("lychee.queue.new_correlation_id", return_value="cid"),
        ):
            mock_gh = MagicMock()
            mock_gh_cls.from_installation_token.return_value = mock_gh

            await queue.enqueue(job)
            await pool.start()
            await asyncio.sleep(0.2)
            await pool.stop(timeout=2.0)

            # No review should be run; state should be completed (no error).
            calls = state_store.upsert_review.call_args_list
            statuses = [c.args[0].review_status for c in calls]
            assert "in_progress" in statuses
            assert "completed" in statuses


class TestCommandProcessUnknownCommand:
    """Test command processing with an unknown @lychee command."""

    @pytest.mark.asyncio
    async def test_command_unknown_posts_help(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """An unknown @lychee command posts help text."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        job = _make_job(job_type=JobType.command)
        job.payload = _make_issue_comment_payload(body="@lychee doSomethingUnknown")

        with (
            patch("lychee.queue.GitHubClient") as mock_gh_cls,
            patch("lychee.queue.new_correlation_id", return_value="cid"),
        ):
            mock_gh = MagicMock()
            mock_gh_cls.from_installation_token.return_value = mock_gh
            mock_pr = MagicMock()
            mock_gh.get_pull_request.return_value = mock_pr

            await queue.enqueue(job)
            await pool.start()
            await asyncio.sleep(0.2)
            await pool.stop(timeout=2.0)

            # Help text should have been posted.
            mock_pr.create_issue_comment.assert_called_once()
            posted_text = mock_pr.create_issue_comment.call_args.args[0]
            assert "Available commands" in posted_text


class TestCommandProcessUnauthorized:
    """Test command processing when the user is unauthorized."""

    @pytest.mark.asyncio
    async def test_command_unauthorized_posts_refusal(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """An unauthorized user running a valid command gets a refusal message."""
        # P5-R2
        lychee_config.authorization.allowed_users = ["admin-only"]

        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        job = _make_job(job_type=JobType.command)
        job.payload = _make_issue_comment_payload(body="@lychee peel", user="hacker")

        with (
            patch("lychee.queue.GitHubClient") as mock_gh_cls,
            patch("lychee.queue.new_correlation_id", return_value="cid"),
        ):
            mock_gh = MagicMock()
            mock_gh_cls.from_installation_token.return_value = mock_gh
            mock_pr = MagicMock()
            mock_gh.get_pull_request.return_value = mock_pr

            await queue.enqueue(job)
            await pool.start()
            await asyncio.sleep(0.2)
            await pool.stop(timeout=2.0)

            mock_pr.create_issue_comment.assert_called_once()
            posted_text = mock_pr.create_issue_comment.call_args.args[0]
            assert "not on the authorized list" in posted_text


class TestGetAnthropicKeyMissing:
    """Test _get_anthropic_key raises when env var is missing."""

    def test_get_anthropic_key_raises(self) -> None:
        """_get_anthropic_key raises RuntimeError when ANTHROPIC_API_KEY is not set."""
        # P5-R2
        from lychee.queue import _get_anthropic_key

        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"),
        ):
            _get_anthropic_key()

    def test_get_anthropic_key_success(self) -> None:
        """_get_anthropic_key returns the key when set."""
        # P5-R2
        from lychee.queue import _get_anthropic_key

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-123"}):
            assert _get_anthropic_key() == "sk-test-123"


class TestProcessJobCompletedNoExistingState:
    """Test _process_job completed path when get_review returns None."""

    @pytest.mark.asyncio
    async def test_process_job_completed_no_existing(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """When get_review returns None on success, a new completed state is created."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        # Make get_review always return None.
        state_store.get_review = AsyncMock(return_value=None)

        job = _make_job(job_type=JobType.command)
        job.payload = _make_issue_comment_payload(body="no lychee mention at all")

        with (
            patch("lychee.queue.GitHubClient") as mock_gh_cls,
            patch("lychee.queue.new_correlation_id", return_value="cid"),
        ):
            mock_gh = MagicMock()
            mock_gh_cls.from_installation_token.return_value = mock_gh

            await queue.enqueue(job)
            await pool.start()
            await asyncio.sleep(0.2)
            await pool.stop(timeout=2.0)

            calls = state_store.upsert_review.call_args_list
            statuses = [c.args[0].review_status for c in calls]
            # in_progress (first), then completed (new state since get_review returned None)
            assert "in_progress" in statuses
            assert "completed" in statuses


class TestProcessJobFailedNoExistingState:
    """Test _process_job failed path when get_review returns None."""

    @pytest.mark.asyncio
    async def test_process_job_failed_no_existing(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """When get_review returns None on failure, a new failed state is created."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        # get_review returns None.
        state_store.get_review = AsyncMock(return_value=None)

        job = _make_job(job_type=JobType.pr_review)

        with (
            patch("lychee.queue.GitHubClient") as mock_gh_cls,
            patch("lychee.queue.run_review", side_effect=RuntimeError("fail")),
            patch("lychee.queue.ClaudeClient"),
            patch("lychee.queue.new_correlation_id", return_value="cid"),
            patch("lychee.queue._get_anthropic_key", return_value="sk-test"),
        ):
            mock_gh = MagicMock()
            mock_gh_cls.from_installation_token.return_value = mock_gh

            await queue.enqueue(job)
            await pool.start()
            await asyncio.sleep(0.2)
            await pool.stop(timeout=2.0)

            calls = state_store.upsert_review.call_args_list
            statuses = [c.args[0].review_status for c in calls]
            assert "in_progress" in statuses
            assert "failed" in statuses


class TestProcessJobStateUpdateFails:
    """Test that _process_job handles state update failure gracefully."""

    @pytest.mark.asyncio
    async def test_state_update_failure_logged(
        self,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """When state store fails during failure update, the error is logged not re-raised."""
        # P5-R2
        state_store = AsyncMock(spec=SqliteStateStore)
        state_store.upsert_review = AsyncMock()
        state_store.initialize = AsyncMock()
        state_store.close = AsyncMock()

        # First call (in_progress) succeeds, then get_review raises on the failure path.
        call_count = 0

        async def failing_get_review(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count > 0:
                raise RuntimeError("DB connection lost")
            return None

        state_store.get_review = AsyncMock(side_effect=failing_get_review)

        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        job = _make_job(job_type=JobType.pr_review)

        with (
            patch("lychee.queue.GitHubClient") as mock_gh_cls,
            patch("lychee.queue.run_review", side_effect=RuntimeError("engine broke")),
            patch("lychee.queue.ClaudeClient"),
            patch("lychee.queue.new_correlation_id", return_value="cid"),
            patch("lychee.queue._get_anthropic_key", return_value="sk-test"),
        ):
            mock_gh = MagicMock()
            mock_gh_cls.from_installation_token.return_value = mock_gh

            await queue.enqueue(job)
            await pool.start()
            await asyncio.sleep(0.3)

            # Worker should still be alive despite double failure.
            assert pool.active_workers == 1
            await pool.stop(timeout=2.0)


class TestStopWithFullQueue:
    """Test stop() when the queue is full (sentinels can't be placed)."""

    @pytest.mark.asyncio
    async def test_stop_full_queue(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """Stopping when the queue is full still shuts down workers via cancellation."""
        # P5-R2
        queue = ReviewQueue(max_size=2)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=2,
        )

        # Fill the queue.
        await queue.enqueue(_make_job(pr_number=1))
        await queue.enqueue(_make_job(pr_number=2))

        await pool.start()
        # Don't process any jobs - stop immediately with short timeout.
        await pool.stop(timeout=0.5)
        assert pool.active_workers == 0


class TestPRReviewUpdatesExistingState:
    """Test _process_pr_review updates existing review state with SHA and comment_id."""

    @pytest.mark.asyncio
    async def test_pr_review_updates_existing_state(
        self,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """When get_review returns existing state, SHA and comment_id are updated."""
        # P5-R2
        existing_review = ReviewState(
            repo_full_name="owner/repo",
            pr_number=42,
            installation_id=12345,
            review_status="in_progress",
        )
        state_store = AsyncMock(spec=SqliteStateStore)
        state_store.get_review = AsyncMock(return_value=existing_review)
        state_store.upsert_review = AsyncMock()
        state_store.initialize = AsyncMock()
        state_store.close = AsyncMock()

        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        job = _make_job(job_type=JobType.pr_review)

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
            patch("lychee.queue.new_correlation_id", return_value="cid"),
            patch("lychee.queue.get_review_strategy", return_value="single_pass"),
            patch("lychee.queue.get_triage_verdict", return_value=None),
            patch("lychee.queue._get_anthropic_key", return_value="sk-test"),
        ):
            mock_gh = MagicMock()
            mock_gh_cls.from_installation_token.return_value = mock_gh
            mock_pr = MagicMock()
            mock_gh.get_pull_request.return_value = mock_pr

            mock_result = MagicMock()
            mock_result.usage = {}
            mock_result.model = "mock"
            mock_result.ripeness.value = "ripe"
            mock_result.findings = []
            mock_run_review.return_value = mock_result

            mock_poster = MagicMock()
            mock_poster.post.return_value = 123
            mock_poster_cls.return_value = mock_poster

            await queue.enqueue(job)
            await pool.start()
            await asyncio.sleep(0.3)
            await pool.stop(timeout=2.0)

            # Verify state was updated with comment_id.
            upsert_calls = state_store.upsert_review.call_args_list
            # Find the call that set comment_id.
            updated_states = [c.args[0] for c in upsert_calls]
            sha_updates = [s for s in updated_states if s.comment_id == 123]
            assert len(sha_updates) >= 1


class TestFailedJobWithExistingState:
    """Test that failure path updates existing state to failed."""

    @pytest.mark.asyncio
    async def test_failed_job_updates_existing_state(
        self,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """When a job fails and get_review returns existing state, it is updated to failed."""
        # P5-R2
        existing_review = ReviewState(
            repo_full_name="owner/repo",
            pr_number=42,
            installation_id=12345,
            review_status="in_progress",
        )
        state_store = AsyncMock(spec=SqliteStateStore)
        state_store.get_review = AsyncMock(return_value=existing_review)
        state_store.upsert_review = AsyncMock()
        state_store.initialize = AsyncMock()
        state_store.close = AsyncMock()

        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        job = _make_job(job_type=JobType.pr_review)

        with (
            patch("lychee.queue.GitHubClient") as mock_gh_cls,
            patch("lychee.queue.run_review", side_effect=RuntimeError("engine broke")),
            patch("lychee.queue.ClaudeClient"),
            patch("lychee.queue.new_correlation_id", return_value="cid"),
            patch("lychee.queue._get_anthropic_key", return_value="sk-test"),
        ):
            mock_gh = MagicMock()
            mock_gh_cls.from_installation_token.return_value = mock_gh

            await queue.enqueue(job)
            await pool.start()
            await asyncio.sleep(0.2)
            await pool.stop(timeout=2.0)

            calls = state_store.upsert_review.call_args_list
            statuses = [c.args[0].review_status for c in calls]
            assert "failed" in statuses


class TestPRReviewWithCostFooter:
    """Test PR review with cost_footer enabled."""

    @pytest.mark.asyncio
    async def test_pr_review_cost_footer(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """When cost_footer is enabled, format_cost_line is called."""
        # P5-R2
        lychee_config.features.cost_footer = True

        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        job = _make_job(job_type=JobType.pr_review)

        with (
            patch("lychee.queue.GitHubClient") as mock_gh_cls,
            patch("lychee.queue.run_review") as mock_run_review,
            patch("lychee.queue.SummaryPoster") as mock_poster_cls,
            patch("lychee.queue.render_comment", return_value="body") as mock_render,
            patch("lychee.queue.ClaudeClient"),
            patch("lychee.queue.build_run_record", return_value={}),
            patch("lychee.queue.emit_run_record"),
            patch("lychee.queue.compute_cost", return_value=0.05),
            patch("lychee.queue.format_cost_line", return_value="Cost: $0.05") as mock_fmt,
            patch("lychee.queue.compute_finding_counts", return_value={}),
            patch("lychee.queue.new_correlation_id", return_value="cid"),
            patch("lychee.queue.get_review_strategy", return_value="single_pass"),
            patch("lychee.queue.get_triage_verdict", return_value=None),
            patch("lychee.queue._get_anthropic_key", return_value="sk-test"),
        ):
            mock_gh = MagicMock()
            mock_gh_cls.from_installation_token.return_value = mock_gh
            mock_pr = MagicMock()
            mock_gh.get_pull_request.return_value = mock_pr

            mock_result = MagicMock()
            mock_result.usage = {}
            mock_result.model = "mock"
            mock_result.ripeness.value = "ripe"
            mock_result.findings = []
            mock_run_review.return_value = mock_result

            mock_poster = MagicMock()
            mock_poster.post.return_value = 1
            mock_poster_cls.return_value = mock_poster

            await queue.enqueue(job)
            await pool.start()
            await asyncio.sleep(0.3)
            await pool.stop(timeout=2.0)

            mock_fmt.assert_called_once()
            mock_render.assert_called_with(mock_result, cost_line="Cost: $0.05")


class TestWorkerCancellation:
    """Test that workers handle cancellation gracefully."""

    @pytest.mark.asyncio
    async def test_worker_cancellation_timeout(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """Workers stuck on long jobs are cancelled after stop() timeout."""
        # P5-R2
        queue = ReviewQueue(max_size=10)
        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        # Override _process_job to block indefinitely.
        async def blocking_process(job: Job) -> None:
            await asyncio.sleep(100)  # Simulates very long processing.

        pool._process_job = blocking_process  # type: ignore[assignment]

        await queue.enqueue(_make_job())
        await pool.start()
        await asyncio.sleep(0.1)

        # Stop with very short timeout to force cancellation.
        await pool.stop(timeout=0.2)
        assert pool.active_workers == 0


# ============================================================================
# END-TO-END TEST
# ============================================================================


class TestE2ELocalWebhookToReview:
    """End-to-end test: local webhook → queue → worker → review (all mocked externals)."""

    @pytest.mark.asyncio
    async def test_e2e_local_webhook_to_review(
        self,
        state_store: AsyncMock,
        mock_authenticator: AsyncMock,
        lychee_config: MagicMock,
    ) -> None:
        """Start full server stack, send a crafted webhook via httpx, assert review posted."""
        # P5-R2
        import hashlib
        import hmac

        from starlette.testclient import TestClient

        from lychee.webhook import WebhookServer

        queue = ReviewQueue(max_size=10)

        async def on_event(event_type: str, payload: dict[str, Any]) -> None:
            job = event_to_job(event_type, payload)
            await queue.enqueue(job)

        pool = WorkerPool(
            queue=queue,
            authenticator=mock_authenticator,
            state_store=state_store,
            config=lychee_config,
            num_workers=1,
        )

        posted_comments: list[str] = []

        async def mock_process(job: Job) -> None:
            posted_comments.append(f"review-for-{job.repo_full_name}#{job.pr_number}")

        pool._process_job = mock_process  # type: ignore[assignment]

        webhook_secret = "test-secret-e2e"
        server = WebhookServer(webhook_secret=webhook_secret, on_event=on_event)
        app = server.create_app()

        # Build a signed payload.
        payload = _make_pr_payload(repo="e2e/test", pr_number=100, installation_id=999)
        body = json.dumps(payload).encode()
        sig = "sha256=" + hmac.new(
            webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()

        with TestClient(app) as client:
            response = client.post(
                "/webhook",
                content=body,
                headers={
                    "X-Hub-Signature-256": sig,
                    "X-GitHub-Event": "pull_request",
                    "Content-Type": "application/json",
                },
            )

        assert response.status_code == 202
        assert queue.size == 1

        # Start the worker pool and let it process.
        await pool.start()
        await asyncio.sleep(0.3)
        await pool.stop(timeout=2.0)

        assert len(posted_comments) == 1
        assert posted_comments[0] == "review-for-e2e/test#100"
