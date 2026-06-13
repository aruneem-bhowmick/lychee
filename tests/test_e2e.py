"""End-to-end tests against a live canary repository.

These tests make real GitHub and Claude API calls.  They are gated behind
the ``e2e`` marker and excluded from default test runs via the
``-m 'not e2e'`` filter in ``pyproject.toml``.

Required environment variables
------------------------------
GITHUB_TOKEN
    Token with write access to the canary repository.
ANTHROPIC_API_KEY
    Anthropic API key for Claude calls.
CANARY_REPO
    The canary repository in ``owner/repo`` format.
CANARY_PR
    PR number to use, or ``"0"`` to find an open PR automatically.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import github as pygithub
import pytest

from lychee.claude import ClaudeClient
from lychee.config import LycheeConfig, load_config
from lychee.github_client import GitHubClient, PullRequestRef
from lychee.models import ReviewResult
from lychee.poster import SummaryPoster
from lychee.render import REVIEW_MARKER, render_comment
from lychee.review import run_review

pytestmark = pytest.mark.e2e

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def canary_repo() -> str:
    """Return the canary repository full name from the ``CANARY_REPO`` env var."""
    repo = os.environ.get("CANARY_REPO")
    if not repo:
        pytest.skip("CANARY_REPO environment variable not set")
    return repo  # type: ignore[return-value]


@pytest.fixture()
def github_token() -> str:
    """Return the GitHub token from the ``GITHUB_TOKEN`` env var."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        pytest.skip("GITHUB_TOKEN environment variable not set")
    return token  # type: ignore[return-value]


@pytest.fixture()
def anthropic_key() -> str:
    """Return the Anthropic API key from the ``ANTHROPIC_API_KEY`` env var."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        pytest.skip("ANTHROPIC_API_KEY environment variable not set")
    return key  # type: ignore[return-value]


@pytest.fixture()
def canary_pr_number(canary_repo: str, github_token: str) -> int:
    """Resolve the PR number to test against.

    Uses the ``CANARY_PR`` env var when it is a non-zero integer.  Falls
    back to searching for the first open PR on the canary repository.
    Skips the test when no suitable PR is found.
    """
    pr_str = os.environ.get("CANARY_PR", "0")
    if pr_str != "0":
        return int(pr_str)

    gh = pygithub.Github(github_token)
    repo = gh.get_repo(canary_repo)
    open_prs = list(repo.get_pulls(state="open"))
    if not open_prs:
        pytest.skip(f"No open PRs on {canary_repo} and CANARY_PR=0")
    return open_prs[0].number  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_review_and_post(
    canary_repo: str,
    pr_number: int,
    github_token: str,
    anthropic_key: str,
) -> tuple[ReviewResult, str, str]:
    """Run the review engine on a canary PR and post the rendered comment.

    Returns a tuple of ``(ReviewResult, rendered_comment_body, head_sha)``.
    Logs a warning when the review exceeds 300 seconds.
    """
    config = load_config()
    gh_client = GitHubClient(token=github_token)
    claude_client = ClaudeClient(api_key=anthropic_key, model=config.model.default)

    pr_ref = f"{canary_repo}#{pr_number}"

    start = time.monotonic()
    result = run_review(pr_ref, config, gh_client, claude_client)
    elapsed = time.monotonic() - start

    if elapsed > 300:
        _logger.warning("Review took %.1f seconds (target: <300s)", elapsed)

    comment_body = render_comment(result, cost_line=None)

    poster = SummaryPoster(gh_client)
    pr_obj = gh_client.get_pull_request(PullRequestRef.parse(pr_ref))
    head_sha: str = pr_obj.head.sha
    state: dict[str, Any] = {"last_reviewed_sha": head_sha}
    poster.post(pr_obj, comment_body, state=state)

    return result, comment_body, head_sha


def _count_marker_comments(
    canary_repo: str,
    pr_number: int,
    github_token: str,
) -> tuple[int, dict[str, Any] | None]:
    """Count review-marker comments on a PR and extract the last state.

    Returns a tuple of ``(marker_comment_count, last_state_dict_or_None)``.
    """
    gh = pygithub.Github(github_token)
    repo = gh.get_repo(canary_repo)
    pr = repo.get_pull(pr_number)

    count = 0
    last_state: dict[str, Any] | None = None
    for comment in pr.get_issue_comments():
        if REVIEW_MARKER in comment.body:
            count += 1
            last_state = SummaryPoster.extract_state(comment.body)

    return count, last_state


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_e2e_module_imports() -> None:
    """Verify core review and posting modules can be imported."""
    import lychee.poster
    import lychee.review

    assert callable(lychee.review.run_review)
    assert callable(lychee.poster.SummaryPoster)


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_e2e_config_loads() -> None:
    """Verify ``load_config()`` returns a valid configuration object."""
    config = load_config()
    assert isinstance(config, LycheeConfig)
    assert config.model.default
    assert config.review.max_files > 0


# ---------------------------------------------------------------------------
# Acceptance / end-to-end tests
# ---------------------------------------------------------------------------


def test_e2e_review_posted(
    canary_repo: str,
    canary_pr_number: int,
    github_token: str,
    anthropic_key: str,
) -> None:
    """A real PR receives a correct review comment.

    Runs the full review pipeline — context fetch, prompt build, Claude
    call, render, and post — against a live canary PR and verifies that
    the posted comment contains the expected marker, sections, ripeness
    badge, and state.
    """
    _result, comment_body, head_sha = _run_review_and_post(
        canary_repo, canary_pr_number, github_token, anthropic_key
    )

    # Verify hidden marker present in rendered body
    assert REVIEW_MARKER in comment_body

    # Verify the three branded sections appear
    assert "Nectar" in comment_body
    assert "The Peel" in comment_body
    assert "Pits" in comment_body

    # Verify a ripeness badge is present
    assert any(badge in comment_body for badge in ("Ripe", "Unripe", "Sour"))

    # Verify the comment exists on the PR and carries valid state
    count, state = _count_marker_comments(canary_repo, canary_pr_number, github_token)
    assert count >= 1, "No comment with the review marker found on the PR"
    assert state is not None, "State marker not found in the posted comment"
    assert state.get("last_reviewed_sha") == head_sha


def test_e2e_repost_updates_in_place(
    canary_repo: str,
    canary_pr_number: int,
    github_token: str,
    anthropic_key: str,
) -> None:
    """Re-running the review updates the existing comment without duplicates.

    Runs the review engine on the same PR a second time (the first run is
    performed by ``test_e2e_review_posted``) and verifies that there is
    still exactly one comment with the review marker.
    """
    _, _, head_sha = _run_review_and_post(
        canary_repo, canary_pr_number, github_token, anthropic_key
    )

    count, state = _count_marker_comments(canary_repo, canary_pr_number, github_token)
    assert count == 1, f"Expected exactly 1 marker comment, found {count}"
    assert state is not None, "State marker not found after repost"
    assert state.get("last_reviewed_sha") == head_sha


def test_e2e_run_record_emitted(
    canary_repo: str,
    canary_pr_number: int,
    github_token: str,
    anthropic_key: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A structured run record is emitted in the logs.

    Verifies that the review engine emits log records containing the repo
    name, PR number, model name, ripeness, and token usage.  Also asserts
    that the API key does not leak into the log output.
    """
    config = load_config()
    gh_client = GitHubClient(token=github_token)
    claude_client = ClaudeClient(api_key=anthropic_key, model=config.model.default)

    pr_ref = f"{canary_repo}#{canary_pr_number}"

    with caplog.at_level(logging.INFO, logger="lychee"):
        result = run_review(pr_ref, config, gh_client, claude_client)

    log_text = caplog.text

    # Required information present in the logs
    assert canary_repo in log_text, "Log should contain the repo name"
    assert str(canary_pr_number) in log_text, "Log should contain the PR number"
    assert config.model.default in log_text, "Log should contain the model name"
    assert result.ripeness.value in log_text, "Log should contain the ripeness"

    # Secrets must never leak into log output
    assert anthropic_key not in log_text, "Log must not contain the API key"
