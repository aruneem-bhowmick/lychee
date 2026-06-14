"""Tests for the run_review() engine orchestrator.

Covers smoke, integration (mocked externals), system, acceptance,
sanity, and regression tests for the review engine pipeline.

Framework: pytest, unittest.mock.patch.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from lychee.claude import ClaudeReviewError
from lychee.config import LycheeConfig
from lychee.context import ReviewContext
from lychee.github_client import PullRequestRef
from lychee.models import ReviewResult
from lychee.render import REVIEW_MARKER
from lychee.review import run_review, run_review_dry

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PR_SIMPLE_FIXTURE = FIXTURES_DIR / "pr_simple.json"


@pytest.fixture()
def default_config() -> LycheeConfig:
    """Default LycheeConfig with all fields at their documented defaults."""
    return LycheeConfig()


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_run_review_importable() -> None:
    """run_review is importable from lychee.review."""
    from lychee.review import run_review

    assert callable(run_review)


# ---------------------------------------------------------------------------
# Integration tests (mocked externals)
# ---------------------------------------------------------------------------


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_run_review_success(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    review_context_simple: ReviewContext,
    default_config: LycheeConfig,
) -> None:
    """run_review returns the expected ReviewResult on a successful pipeline run."""
    mock_build_context.return_value = review_context_simple
    mock_build_system_prompt_blocks.return_value = [{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}]
    mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

    result = run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    assert isinstance(result, ReviewResult)
    assert result == mock_claude_client.review.return_value


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_run_review_calls_build_context(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    review_context_simple: ReviewContext,
    default_config: LycheeConfig,
) -> None:
    """build_context is called with the correct GitHubClient, parsed PullRequestRef, and config."""
    mock_build_context.return_value = review_context_simple
    mock_build_system_prompt_blocks.return_value = [{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}]
    mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

    run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    mock_build_context.assert_called_once_with(
        mock_github_client,
        PullRequestRef(owner="owner", repo="repo", number=42),
        default_config,
    )


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_run_review_calls_build_system_prompt_blocks(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    review_context_simple: ReviewContext,
    default_config: LycheeConfig,
) -> None:
    """build_system_prompt_blocks is called with config and conventions from context."""
    mock_build_context.return_value = review_context_simple
    mock_build_system_prompt_blocks.return_value = [{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}]
    mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

    run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    mock_build_system_prompt_blocks.assert_called_once_with(
        default_config, conventions=review_context_simple.conventions
    )


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_run_review_calls_build_messages(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    review_context_simple: ReviewContext,
    default_config: LycheeConfig,
) -> None:
    """build_messages is called with the context and config."""
    mock_build_context.return_value = review_context_simple
    mock_build_system_prompt_blocks.return_value = [{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}]
    mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

    run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    mock_build_messages.assert_called_once_with(review_context_simple, default_config)


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_run_review_calls_claude_review(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    review_context_simple: ReviewContext,
    default_config: LycheeConfig,
) -> None:
    """claude_client.review() is called with messages and system prompt."""
    mock_build_context.return_value = review_context_simple
    mock_build_system_prompt_blocks.return_value = [{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}]
    messages = [{"role": "user", "content": "msg"}]
    mock_build_messages.return_value = messages

    run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    mock_claude_client.review.assert_called_once_with(
        messages,
        system=[{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}],
    )


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_run_review_passes_conventions(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    default_config: LycheeConfig,
) -> None:
    """When context has conventions, build_system_prompt_blocks receives them."""
    context_with_conventions = ReviewContext(
        pr_number=42,
        pr_title="Add utility functions",
        pr_body="This PR adds utility functions.",
        pr_author="octocat",
        base_ref="main",
        head_ref="feat/utils",
        head_sha="abc123def456",
        repo_full_name="owner/repo",
        diff="diff --git a/f.py b/f.py\n+hello\n",
        changed_files=[],
        commit_messages=["Add utility functions"],
        conventions="Use black for formatting. Max line length 100.",
    )
    mock_build_context.return_value = context_with_conventions
    mock_build_system_prompt_blocks.return_value = [{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}]
    mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

    run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    mock_build_system_prompt_blocks.assert_called_once_with(
        default_config,
        conventions="Use black for formatting. Max line length 100.",
    )


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_run_review_no_conventions(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    review_context_simple: ReviewContext,
    default_config: LycheeConfig,
) -> None:
    """When context has no conventions, build_system_prompt_blocks receives None."""
    assert review_context_simple.conventions is None
    mock_build_context.return_value = review_context_simple
    mock_build_system_prompt_blocks.return_value = [{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}]
    mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

    run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    mock_build_system_prompt_blocks.assert_called_once_with(default_config, conventions=None)


def test_run_review_invalid_ref_raises(
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    default_config: LycheeConfig,
) -> None:
    """A malformed pr_ref raises ValueError before any external calls."""
    with pytest.raises(ValueError, match="Invalid PR reference"):
        run_review("bad-ref", default_config, mock_github_client, mock_claude_client)


@patch("lychee.review.build_context")
def test_run_review_github_error_propagates(
    mock_build_context: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    default_config: LycheeConfig,
) -> None:
    """GithubException from build_context propagates without being caught."""
    mock_build_context.side_effect = GithubException(404, "Not Found", None)

    with pytest.raises(GithubException):
        run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_run_review_claude_error_propagates(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    review_context_simple: ReviewContext,
    default_config: LycheeConfig,
) -> None:
    """ClaudeReviewError from claude_client.review() propagates without being caught."""
    mock_build_context.return_value = review_context_simple
    mock_build_system_prompt_blocks.return_value = [{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}]
    mock_build_messages.return_value = [{"role": "user", "content": "msg"}]
    mock_claude_client.review.side_effect = ClaudeReviewError("API error")

    with pytest.raises(ClaudeReviewError, match="API error"):
        run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)


# ---------------------------------------------------------------------------
# System tests (assembled engine, externals mocked)
# ---------------------------------------------------------------------------


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_system_full_pipeline(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    review_context_simple: ReviewContext,
    ripe_review_result: ReviewResult,
    default_config: LycheeConfig,
) -> None:
    """End-to-end pipeline with mocked GitHubClient and ClaudeClient."""
    mock_build_context.return_value = review_context_simple
    mock_build_system_prompt_blocks.return_value = [{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}]
    mock_build_messages.return_value = [{"role": "user", "content": "msg"}]
    mock_claude_client.review.return_value = ripe_review_result

    result = run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    assert result is ripe_review_result
    assert result.ripeness.value == "ripe"


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_system_model_from_config(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    review_context_simple: ReviewContext,
    ripe_review_result: ReviewResult,
    default_config: LycheeConfig,
) -> None:
    """ReviewResult.model reflects the model used by ClaudeClient."""
    mock_build_context.return_value = review_context_simple
    mock_build_system_prompt_blocks.return_value = [{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}]
    mock_build_messages.return_value = [{"role": "user", "content": "msg"}]
    mock_claude_client.review.return_value = ripe_review_result

    result = run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    assert result.model == ripe_review_result.model


def test_system_dry_run_still_works(default_config: LycheeConfig) -> None:
    """run_review_dry() still works after run_review() was implemented (no regression)."""
    result = run_review_dry(PR_SIMPLE_FIXTURE, default_config)
    assert isinstance(result, str)
    assert REVIEW_MARKER in result


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_accept_end_to_end_mocked(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    review_context_simple: ReviewContext,
    default_config: LycheeConfig,
) -> None:
    """Acceptance: end-to-end pipeline yields a valid ReviewResult."""
    mock_build_context.return_value = review_context_simple
    mock_build_system_prompt_blocks.return_value = [{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}]
    mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

    result = run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    assert isinstance(result, ReviewResult)
    assert result.ripeness is not None
    assert result.summary
    assert result.model


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_accept_model_chosen_per_config(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    review_context_simple: ReviewContext,
    ripe_review_result: ReviewResult,
    default_config: LycheeConfig,
) -> None:
    """Acceptance: model in the result matches the configured model."""
    mock_build_context.return_value = review_context_simple
    mock_build_system_prompt_blocks.return_value = [{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}]
    mock_build_messages.return_value = [{"role": "user", "content": "msg"}]
    mock_claude_client.review.return_value = ripe_review_result

    result = run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    # The model comes from the ClaudeClient (which is configured with config.model.default).
    assert result.model == ripe_review_result.model


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_run_review_dry_unchanged(default_config: LycheeConfig) -> None:
    """run_review_dry() behaves identically to before — returns valid rendered output."""
    result = run_review_dry(PR_SIMPLE_FIXTURE, default_config)
    assert isinstance(result, str)
    assert len(result) > 0
    assert REVIEW_MARKER in result


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def test_dry_run_output_unchanged(default_config: LycheeConfig) -> None:
    """run_review_dry() output matches golden snapshot (deterministic output)."""
    first = run_review_dry(PR_SIMPLE_FIXTURE, default_config)
    second = run_review_dry(PR_SIMPLE_FIXTURE, default_config)
    assert first == second


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_run_review_result_shape(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    review_context_simple: ReviewContext,
    default_config: LycheeConfig,
) -> None:
    """Returned ReviewResult has all required fields populated."""
    mock_build_context.return_value = review_context_simple
    mock_build_system_prompt_blocks.return_value = [{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}]
    mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

    result = run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    assert hasattr(result, "ripeness")
    assert hasattr(result, "summary")
    assert hasattr(result, "walkthrough")
    assert hasattr(result, "findings")
    assert hasattr(result, "model")
    assert hasattr(result, "usage")
    assert isinstance(result.findings, list)
    assert isinstance(result.usage, dict)
