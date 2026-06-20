"""Async job queue and worker pool for processing GitHub webhook events.

Provides an in-process async queue with backpressure and a configurable
worker pool that dequeues jobs, obtains per-installation authentication,
runs the unchanged Lychee review engine, posts results, and updates
durable state.  The queue bridges the webhook server to the engine:
events are enqueued on receipt and processed concurrently by workers.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from lychee.app_auth import AppAuthenticator
from lychee.authorization import format_refusal, is_authorized
from lychee.claude import ClaudeClient
from lychee.command_render import COMMAND_RENDERERS
from lychee.commands import HELP_TEXT, UnknownCommand, parse_command
from lychee.config import LycheeConfig
from lychee.cost import compute_cost, format_cost_line
from lychee.github_client import GitHubClient, PullRequestRef
from lychee.observability import (
    build_run_record,
    compute_finding_counts,
    emit_run_record,
    get_review_strategy,
    get_triage_verdict,
    new_correlation_id,
)
from lychee.poster import SummaryPoster
from lychee.render import render_comment
from lychee.review import run_review
from lychee.state_store import ReviewState, StateStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job model
# ---------------------------------------------------------------------------


class JobType(StrEnum):
    """Types of jobs the queue can process."""

    pr_review = "pr_review"
    command = "command"


@dataclass
class Job:
    """A unit of work for the worker pool."""

    job_id: str
    job_type: JobType
    installation_id: int
    repo_full_name: str
    pr_number: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class QueueFullError(Exception):
    """Raised when the queue is at capacity and cannot accept new jobs."""


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


class ReviewQueue:
    """Async job queue with backpressure.

    Wraps ``asyncio.Queue`` with a maximum size.  When the queue is full,
    ``enqueue`` raises ``QueueFullError`` instead of blocking, enforcing
    backpressure at the webhook layer (HTTP 503).
    """

    def __init__(self, max_size: int = 100) -> None:
        """Initialize with a maximum queue size.

        Args:
            max_size: Maximum number of pending jobs.  Enqueue raises
                      ``QueueFullError`` when this limit is reached.
        """
        self._queue: asyncio.Queue[Job | None] = asyncio.Queue(maxsize=max_size)
        self._max_size = max_size

    async def enqueue(self, job: Job) -> None:
        """Add a job to the queue.

        Raises:
            QueueFullError: If the queue is at capacity.
        """
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull as err:
            raise QueueFullError(
                f"Queue is full (max_size={self._max_size}); cannot accept job {job.job_id}"
            ) from err
        logger.info(
            "Job enqueued: job_id=%s repo=%s pr=%d type=%s queue_size=%d",
            job.job_id,
            job.repo_full_name,
            job.pr_number,
            job.job_type.value,
            self.size,
        )

    async def dequeue(self) -> Job | None:
        """Remove and return the next job.  Blocks until a job is available.

        Returns ``None`` only when a sentinel is received during shutdown.
        """
        return await self._queue.get()

    @property
    def size(self) -> int:
        """Current number of pending jobs."""
        return self._queue.qsize()

    @property
    def is_full(self) -> bool:
        """True if the queue is at capacity."""
        return self._queue.full()


# ---------------------------------------------------------------------------
# Worker pool
# ---------------------------------------------------------------------------


class WorkerPool:
    """Pool of async workers that process jobs from the queue.

    Each worker loops: dequeue a job, authenticate with the installation,
    invoke the review engine (or command dispatcher), post results, and
    update durable state.  Workers catch all exceptions to stay alive.
    """

    def __init__(
        self,
        queue: ReviewQueue,
        authenticator: AppAuthenticator,
        state_store: StateStore,
        config: LycheeConfig,
        num_workers: int = 4,
    ) -> None:
        """Initialize the worker pool.

        Args:
            queue: The job queue to consume from.
            authenticator: For obtaining installation tokens.
            state_store: For tracking review state.
            config: Lychee configuration (model, review settings, etc.).
            num_workers: Number of concurrent worker tasks.
        """
        self._queue = queue
        self._authenticator = authenticator
        self._state_store = state_store
        self._config = config
        self._num_workers = num_workers
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False

    async def start(self) -> None:
        """Start all worker tasks.  Idempotent (no-op if already running)."""
        if self._running:
            return
        self._running = True
        self._tasks = [
            asyncio.create_task(self._worker(i), name=f"worker-{i}")
            for i in range(self._num_workers)
        ]
        logger.info("Worker pool started: %d workers", self._num_workers)

    async def stop(self, timeout: float = 30.0) -> None:
        """Signal workers to stop and wait for graceful shutdown.

        Places sentinel ``None`` values in the queue to unblock waiting
        workers, then waits up to *timeout* seconds for them to finish.
        Any tasks still running after the timeout are cancelled.

        Args:
            timeout: Maximum seconds to wait for workers to finish current jobs.
        """
        self._running = False

        # Unblock workers waiting on the queue.
        for _ in range(self._num_workers):
            with contextlib.suppress(asyncio.QueueFull):
                self._queue._queue.put_nowait(None)

        if self._tasks:
            _done, pending = await asyncio.wait(self._tasks, timeout=timeout)
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        self._tasks.clear()
        logger.info("Worker pool stopped")

    async def _worker(self, worker_id: int) -> None:
        """Main worker loop: dequeue, process, repeat until stopped."""
        logger.info("Worker %d started", worker_id)
        while self._running:
            try:
                item = await self._queue.dequeue()
                if item is None:
                    # Sentinel received; exit.
                    break
                await self._process_job(item)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Worker %d encountered an unexpected error", worker_id)
        logger.info("Worker %d stopped", worker_id)

    async def _process_job(self, job: Job) -> None:
        """Process a single job: authenticate, run engine, post result, update state.

        On success the state is updated to ``completed``.
        On failure the state is updated to ``failed`` and the error is logged.
        The exception is not re-raised so the worker stays alive.
        """
        logger.info(
            "Processing job: job_id=%s repo=%s pr=%d type=%s",
            job.job_id,
            job.repo_full_name,
            job.pr_number,
            job.job_type.value,
        )

        # Mark as in_progress.
        await self._state_store.upsert_review(
            ReviewState(
                repo_full_name=job.repo_full_name,
                pr_number=job.pr_number,
                installation_id=job.installation_id,
                review_status="in_progress",
            )
        )

        try:
            if job.job_type == JobType.pr_review:
                await self._process_pr_review(job)
            elif job.job_type == JobType.command:
                await self._process_command(job)

            # Mark as completed.
            now = datetime.now(UTC).isoformat()
            existing = await self._state_store.get_review(job.repo_full_name, job.pr_number)
            if existing is not None:
                existing.review_status = "completed"
                existing.updated_at = now
                await self._state_store.upsert_review(existing)
            else:
                await self._state_store.upsert_review(
                    ReviewState(
                        repo_full_name=job.repo_full_name,
                        pr_number=job.pr_number,
                        installation_id=job.installation_id,
                        review_status="completed",
                        updated_at=now,
                    )
                )

            logger.info(
                "Job completed: job_id=%s repo=%s pr=%d",
                job.job_id,
                job.repo_full_name,
                job.pr_number,
            )
        except Exception:
            logger.exception(
                "Job failed: job_id=%s repo=%s pr=%d",
                job.job_id,
                job.repo_full_name,
                job.pr_number,
            )
            now = datetime.now(UTC).isoformat()
            try:
                existing = await self._state_store.get_review(
                    job.repo_full_name, job.pr_number
                )
                if existing is not None:
                    existing.review_status = "failed"
                    existing.updated_at = now
                    await self._state_store.upsert_review(existing)
                else:
                    await self._state_store.upsert_review(
                        ReviewState(
                            repo_full_name=job.repo_full_name,
                            pr_number=job.pr_number,
                            installation_id=job.installation_id,
                            review_status="failed",
                            updated_at=now,
                        )
                    )
            except Exception:
                logger.exception(
                    "Failed to update state to 'failed' for job_id=%s", job.job_id
                )

    async def _process_pr_review(self, job: Job) -> None:
        """Handle a pr_review job: fetch context, run review, post comment.

        Obtains an installation token, creates an authenticated GitHub
        client, builds the review context, invokes the engine, and posts
        the result.  Updates the state store with the reviewed SHA and
        comment ID.
        """
        new_correlation_id()

        token = await self._authenticator.get_installation_token(job.installation_id)
        gh = GitHubClient.from_installation_token(token.token)

        pr_ref_str = f"{job.repo_full_name}#{job.pr_number}"
        parsed_ref = PullRequestRef.parse(pr_ref_str)

        repo_config = self._config

        anthropic_key = _get_anthropic_key()
        claude_client = ClaudeClient(api_key=anthropic_key, model=repo_config.model.default)

        start = time.monotonic()
        result = run_review(pr_ref_str, repo_config, gh, claude_client)
        duration = time.monotonic() - start

        cost_usd = compute_cost(result.usage, result.model)
        cost_line: str | None = None
        if repo_config.features.cost_footer:
            cost_line = format_cost_line(cost_usd, result.usage)

        comment_body = render_comment(result, cost_line=cost_line)

        poster = SummaryPoster(gh)
        pr = gh.get_pull_request(parsed_ref)
        comment_id = poster.post(pr, comment_body)

        # Update state with SHA and comment ID.
        head_sha = job.payload.get("pull_request", {}).get("head", {}).get("sha", "")
        now = datetime.now(UTC).isoformat()
        existing = await self._state_store.get_review(job.repo_full_name, job.pr_number)
        if existing is not None:
            existing.last_reviewed_sha = head_sha
            existing.comment_id = comment_id
            existing.updated_at = now
            await self._state_store.upsert_review(existing)

        # Emit structured run record.
        record = build_run_record(
            repo=job.repo_full_name,
            pr_number=job.pr_number,
            head_sha=head_sha,
            model=result.model,
            usage=result.usage,
            cost_usd=cost_usd,
            ripeness=result.ripeness.value,
            finding_counts=compute_finding_counts(result.findings),
            duration_seconds=duration,
            review_strategy=get_review_strategy(),
            triage_verdict=get_triage_verdict(),
        )
        emit_run_record(record)

    async def _process_command(self, job: Job) -> None:
        """Handle a command job: parse command, check auth, dispatch.

        Extracts the comment body from the payload, uses the existing
        ``parse_command`` and ``is_authorized`` logic, and dispatches
        via an installation-token-authenticated GitHub client.
        """
        new_correlation_id()

        token = await self._authenticator.get_installation_token(job.installation_id)
        gh = GitHubClient.from_installation_token(token.token)

        comment_body = job.payload.get("comment", {}).get("body", "")
        comment_author = job.payload.get("comment", {}).get("user", {}).get("login", "")

        parsed = parse_command(comment_body)
        if parsed is None:
            return

        if isinstance(parsed, UnknownCommand):
            pr_ref = PullRequestRef.parse(f"{job.repo_full_name}#{job.pr_number}")
            pr = gh.get_pull_request(pr_ref)
            pr.create_issue_comment(HELP_TEXT)
            return

        if not is_authorized(comment_author, self._config):
            pr_ref = PullRequestRef.parse(f"{job.repo_full_name}#{job.pr_number}")
            pr = gh.get_pull_request(pr_ref)
            pr.create_issue_comment(format_refusal(comment_author))
            return

        # Dispatch the command.
        pr_ref_str = f"{job.repo_full_name}#{job.pr_number}"

        anthropic_key = _get_anthropic_key()
        claude_client = ClaudeClient(api_key=anthropic_key, model=self._config.model.default)

        result = run_review(pr_ref_str, self._config, gh, claude_client)
        renderer = COMMAND_RENDERERS[parsed.command.value]
        response = renderer(result)

        pr_ref = PullRequestRef.parse(pr_ref_str)
        pr = gh.get_pull_request(pr_ref)
        pr.create_issue_comment(response)

    @property
    def active_workers(self) -> int:
        """Number of currently running worker tasks."""
        return sum(1 for t in self._tasks if not t.done())


# ---------------------------------------------------------------------------
# Event-to-job conversion
# ---------------------------------------------------------------------------


def event_to_job(event_type: str, payload: dict[str, Any]) -> Job:
    """Convert a validated webhook event into a Job.

    Extracts ``installation_id``, repo full name, and PR number from the
    payload.  Generates a unique ``job_id`` using ``uuid.uuid4().hex``.

    Args:
        event_type: GitHub event type (e.g. ``"pull_request"``, ``"issue_comment"``).
        payload: Parsed webhook JSON payload.

    Returns:
        A Job ready for enqueuing.

    Raises:
        ValueError: If required fields are missing from the payload.
    """
    # Extract installation_id.
    installation = payload.get("installation")
    if installation is None or "id" not in installation:
        raise ValueError("Missing 'installation.id' in webhook payload")
    installation_id: int = installation["id"]

    # Extract repository full_name.
    repository = payload.get("repository")
    if repository is None or "full_name" not in repository:
        raise ValueError("Missing 'repository.full_name' in webhook payload")
    repo_full_name: str = repository["full_name"]

    # Extract PR number and determine job type.
    if event_type == "pull_request":
        pr_data = payload.get("pull_request")
        if pr_data is None or "number" not in pr_data:
            raise ValueError("Missing 'pull_request.number' in webhook payload")
        pr_number: int = pr_data["number"]
        job_type = JobType.pr_review
    elif event_type == "issue_comment":
        issue_data = payload.get("issue")
        if issue_data is None or "number" not in issue_data:
            raise ValueError("Missing 'issue.number' in webhook payload")
        pr_number = issue_data["number"]
        job_type = JobType.command
    else:
        raise ValueError(f"Unsupported event type: {event_type!r}")

    return Job(
        job_id=uuid.uuid4().hex,
        job_type=job_type,
        installation_id=installation_id,
        repo_full_name=repo_full_name,
        pr_number=pr_number,
        event_type=event_type,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_anthropic_key() -> str:
    """Read the Anthropic API key from the environment.

    Raises:
        RuntimeError: If ``ANTHROPIC_API_KEY`` is not set.
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")
    return key
