"""Tests for the run_review() engine orchestrator.

Covers smoke, integration (mocked externals), system, acceptance,
sanity, and regression tests for the review engine pipeline.

Framework: pytest, unittest.mock.patch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from lychee.claude import ClaudeReviewError
from lychee.config import LycheeConfig
from lychee.context import ReviewContext
from lychee.cost import BudgetExceededError
from lychee.github_client import PullRequestRef
from lychee.models import ReviewResult, Ripeness
from lychee.render import REVIEW_MARKER
from lychee.review import (
    _LARGE_PR_THRESHOLD,
    _MAP_GROUP_SIZE,
    _aggregate_usage,
    _compute_context_size,
    _filter_diff_for_files,
    _partition_files,
    _should_map_reduce,
    run_review,
    run_review_dry,
    select_model,
)

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
    mock_build_system_prompt_blocks.return_value = [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
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
    mock_build_system_prompt_blocks.return_value = [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
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
    mock_build_system_prompt_blocks.return_value = [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
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
    mock_build_system_prompt_blocks.return_value = [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
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
    mock_build_system_prompt_blocks.return_value = [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
    messages = [{"role": "user", "content": "msg"}]
    mock_build_messages.return_value = messages

    run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    mock_claude_client.review.assert_called_once_with(
        messages,
        system=[{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}],
        model_override="claude-sonnet-4-6",
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
    mock_build_system_prompt_blocks.return_value = [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
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
    mock_build_system_prompt_blocks.return_value = [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
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
    mock_build_system_prompt_blocks.return_value = [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
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
    mock_build_system_prompt_blocks.return_value = [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
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
    mock_build_system_prompt_blocks.return_value = [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
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
    mock_build_system_prompt_blocks.return_value = [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
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
    mock_build_system_prompt_blocks.return_value = [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
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
    mock_build_system_prompt_blocks.return_value = [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
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


# ---------------------------------------------------------------------------
# Prompt caching tests
# ---------------------------------------------------------------------------


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_system_run_review_uses_cache_blocks(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    review_context_simple: ReviewContext,
    default_config: LycheeConfig,
) -> None:
    """run_review passes a list (not a string) to claude_client.review() as system."""
    mock_build_context.return_value = review_context_simple
    blocks = [{"type": "text", "text": "cached", "cache_control": {"type": "ephemeral"}}]
    mock_build_system_prompt_blocks.return_value = blocks
    mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

    run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    call_args = mock_claude_client.review.call_args
    system_arg = call_args.kwargs["system"]
    assert isinstance(system_arg, list)
    assert system_arg[0]["cache_control"] == {"type": "ephemeral"}


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_run_review_calls_build_system_prompt_blocks_integration(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    review_context_simple: ReviewContext,
    default_config: LycheeConfig,
) -> None:
    """run_review calls build_system_prompt_blocks (not build_system_prompt)."""
    mock_build_context.return_value = review_context_simple
    mock_build_system_prompt_blocks.return_value = [
        {"type": "text", "text": "prompt", "cache_control": {"type": "ephemeral"}}
    ]
    mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

    run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    mock_build_system_prompt_blocks.assert_called_once()


@patch("lychee.review.build_messages")
@patch("lychee.review.build_system_prompt_blocks")
@patch("lychee.review.build_context")
def test_accept_cost_data_available(
    mock_build_context: MagicMock,
    mock_build_system_prompt_blocks: MagicMock,
    mock_build_messages: MagicMock,
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
    review_context_simple: ReviewContext,
    default_config: LycheeConfig,
) -> None:
    """ReviewResult from run_review includes usage data for cost tracking."""
    mock_build_context.return_value = review_context_simple
    mock_build_system_prompt_blocks.return_value = [
        {"type": "text", "text": "prompt", "cache_control": {"type": "ephemeral"}}
    ]
    mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

    result = run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

    assert isinstance(result.usage, dict)
    assert "input_tokens" in result.usage
    assert "output_tokens" in result.usage


# ---------------------------------------------------------------------------
# Model tiering tests
# ---------------------------------------------------------------------------


class TestModelTiering:
    """Tests for select_model() and context-size-based model selection."""

    def test_select_model_default(self, default_config: LycheeConfig) -> None:
        """Context below threshold returns config.model.default."""
        result = select_model(default_config, context_size=1000)
        assert result == default_config.model.default

    def test_select_model_large_pr(self, default_config: LycheeConfig) -> None:
        """Context above threshold returns config.model.large_pr."""
        result = select_model(default_config, context_size=_LARGE_PR_THRESHOLD + 1)
        assert result == default_config.model.large_pr

    def test_select_model_at_boundary(self, default_config: LycheeConfig) -> None:
        """Context exactly at threshold returns default (exclusive boundary)."""
        result = select_model(default_config, context_size=_LARGE_PR_THRESHOLD)
        assert result == default_config.model.default

    def test_compute_context_size_simple(self, review_context_simple: ReviewContext) -> None:
        """_compute_context_size sums diff and content_at_head."""
        size = _compute_context_size(review_context_simple)
        expected = len(review_context_simple.diff)
        for f in review_context_simple.changed_files:
            if f.get("content_at_head") is not None:
                expected += len(f["content_at_head"])
        assert size == expected

    @patch("lychee.review.build_messages")
    @patch("lychee.review.build_system_prompt_blocks")
    @patch("lychee.review.build_context")
    def test_run_review_model_tiering_large(
        self,
        mock_build_context: MagicMock,
        mock_build_system_prompt_blocks: MagicMock,
        mock_build_messages: MagicMock,
        mock_github_client: MagicMock,
        mock_claude_client: MagicMock,
        default_config: LycheeConfig,
    ) -> None:
        """Integration: large context triggers large_pr model override."""
        # Create a context with a very large diff
        large_context = ReviewContext(
            pr_number=42,
            pr_title="Big PR",
            pr_body="Large changes.",
            pr_author="dev",
            base_ref="main",
            head_ref="feat/big",
            head_sha="abc123",
            repo_full_name="owner/repo",
            diff="x" * (_LARGE_PR_THRESHOLD + 1),
            changed_files=[],
            commit_messages=["big change"],
            conventions=None,
        )
        mock_build_context.return_value = large_context
        mock_build_system_prompt_blocks.return_value = [
            {"type": "text", "text": "prompt", "cache_control": {"type": "ephemeral"}}
        ]
        mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

        run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

        call_kwargs = mock_claude_client.review.call_args.kwargs
        assert call_kwargs["model_override"] == default_config.model.large_pr

    @patch("lychee.review.build_messages")
    @patch("lychee.review.build_system_prompt_blocks")
    @patch("lychee.review.build_context")
    def test_run_review_default_model(
        self,
        mock_build_context: MagicMock,
        mock_build_system_prompt_blocks: MagicMock,
        mock_build_messages: MagicMock,
        mock_github_client: MagicMock,
        mock_claude_client: MagicMock,
        review_context_simple: ReviewContext,
        default_config: LycheeConfig,
    ) -> None:
        """Integration: small context uses default model override."""
        mock_build_context.return_value = review_context_simple
        mock_build_system_prompt_blocks.return_value = [
            {"type": "text", "text": "prompt", "cache_control": {"type": "ephemeral"}}
        ]
        mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

        run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

        call_kwargs = mock_claude_client.review.call_args.kwargs
        assert call_kwargs["model_override"] == default_config.model.default

    @patch("lychee.review.build_messages")
    @patch("lychee.review.build_system_prompt_blocks")
    @patch("lychee.review.build_context")
    def test_accept_tiering_selects_models(
        self,
        mock_build_context: MagicMock,
        mock_build_system_prompt_blocks: MagicMock,
        mock_build_messages: MagicMock,
        mock_github_client: MagicMock,
        mock_claude_client: MagicMock,
        default_config: LycheeConfig,
    ) -> None:
        """Acceptance: both model paths (default and large_pr) are verified."""
        mock_build_system_prompt_blocks.return_value = [
            {"type": "text", "text": "prompt", "cache_control": {"type": "ephemeral"}}
        ]
        mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

        # Small context → default model
        small_context = ReviewContext(
            pr_number=1,
            pr_title="Small",
            pr_body=None,
            pr_author="dev",
            base_ref="main",
            head_ref="fix",
            head_sha="000",
            repo_full_name="owner/repo",
            diff="small diff",
            changed_files=[],
            commit_messages=[],
            conventions=None,
        )
        mock_build_context.return_value = small_context
        run_review("owner/repo#1", default_config, mock_github_client, mock_claude_client)
        assert mock_claude_client.review.call_args.kwargs["model_override"] == "claude-sonnet-4-6"

        mock_claude_client.reset_mock()

        # Large context → large_pr model
        large_context = ReviewContext(
            pr_number=2,
            pr_title="Large",
            pr_body=None,
            pr_author="dev",
            base_ref="main",
            head_ref="feat",
            head_sha="111",
            repo_full_name="owner/repo",
            diff="x" * (_LARGE_PR_THRESHOLD + 1),
            changed_files=[],
            commit_messages=[],
            conventions=None,
        )
        mock_build_context.return_value = large_context
        run_review("owner/repo#2", default_config, mock_github_client, mock_claude_client)
        assert mock_claude_client.review.call_args.kwargs["model_override"] == "claude-opus-4-8"

    def test_default_config_behavior_unchanged(self, default_config: LycheeConfig) -> None:
        """Sanity: default config with small context selects the default model."""
        model = select_model(default_config, context_size=500)
        assert model == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Map-reduce: smoke
# ---------------------------------------------------------------------------


def test_map_reduce_functions_importable() -> None:
    """All map-reduce helpers are importable from lychee.review."""
    from lychee.review import (
        _MAP_GROUP_SIZE,
        _MAP_REDUCE_FILE_THRESHOLD,
        _aggregate_usage,
        _filter_diff_for_files,
        _partition_files,
        _should_map_reduce,
    )

    assert callable(_should_map_reduce)
    assert callable(_partition_files)
    assert callable(_filter_diff_for_files)
    assert callable(_aggregate_usage)
    assert isinstance(_MAP_GROUP_SIZE, int)
    assert isinstance(_MAP_REDUCE_FILE_THRESHOLD, int)


# ---------------------------------------------------------------------------
# Map-reduce: sanity
# ---------------------------------------------------------------------------


def test_small_pr_not_map_reduced(
    review_context_simple: ReviewContext,
    default_config: LycheeConfig,
) -> None:
    """A small PR (1 file) does not trigger map-reduce."""
    assert not _should_map_reduce(review_context_simple, default_config)


# ---------------------------------------------------------------------------
# Map-reduce: _should_map_reduce
# ---------------------------------------------------------------------------


class TestShouldMapReduce:
    """Tests for the _should_map_reduce decision function."""

    def test_above_threshold(
        self, review_context_large: ReviewContext, default_config: LycheeConfig
    ) -> None:
        """62 files > 50 threshold → should map-reduce."""
        assert _should_map_reduce(review_context_large, default_config)

    def test_below_threshold(
        self, review_context_simple: ReviewContext, default_config: LycheeConfig
    ) -> None:
        """1 file < 50 threshold → should not map-reduce."""
        assert not _should_map_reduce(review_context_simple, default_config)

    def test_at_threshold(self, default_config: LycheeConfig) -> None:
        """Exactly 50 files (at threshold, exclusive) → should not map-reduce."""
        files = [{"filename": f"f{i}.py"} for i in range(50)]
        ctx = ReviewContext(
            pr_number=1,
            pr_title="At threshold",
            pr_body=None,
            pr_author="dev",
            base_ref="main",
            head_ref="fix",
            head_sha="000",
            repo_full_name="o/r",
            diff="",
            changed_files=files,
            commit_messages=[],
            conventions=None,
        )
        assert not _should_map_reduce(ctx, default_config)

    def test_custom_config(self) -> None:
        """Custom max_files=5 triggers map-reduce for 6 files."""
        config = LycheeConfig(review={"max_files": 5})  # type: ignore[arg-type]
        files = [{"filename": f"f{i}.py"} for i in range(6)]
        ctx = ReviewContext(
            pr_number=1,
            pr_title="Custom",
            pr_body=None,
            pr_author="dev",
            base_ref="main",
            head_ref="fix",
            head_sha="000",
            repo_full_name="o/r",
            diff="",
            changed_files=files,
            commit_messages=[],
            conventions=None,
        )
        assert _should_map_reduce(ctx, config)

    def test_empty_files(self, default_config: LycheeConfig) -> None:
        """Zero files → should not map-reduce."""
        ctx = ReviewContext(
            pr_number=1,
            pr_title="Empty",
            pr_body=None,
            pr_author="dev",
            base_ref="main",
            head_ref="fix",
            head_sha="000",
            repo_full_name="o/r",
            diff="",
            changed_files=[],
            commit_messages=[],
            conventions=None,
        )
        assert not _should_map_reduce(ctx, default_config)


# ---------------------------------------------------------------------------
# Map-reduce: _partition_files
# ---------------------------------------------------------------------------


class TestPartitionFiles:
    """Tests for the _partition_files chunking function."""

    def test_even_split(self) -> None:
        """20 files split by 10 → 2 groups of 10."""
        files = [{"filename": f"f{i}.py"} for i in range(20)]
        groups = _partition_files(files, 10)
        assert len(groups) == 2
        assert all(len(g) == 10 for g in groups)

    def test_uneven_split(self) -> None:
        """15 files split by 10 → groups of 10 and 5."""
        files = [{"filename": f"f{i}.py"} for i in range(15)]
        groups = _partition_files(files, 10)
        assert len(groups) == 2
        assert len(groups[0]) == 10
        assert len(groups[1]) == 5

    def test_single_group(self) -> None:
        """5 files split by 10 → 1 group of 5."""
        files = [{"filename": f"f{i}.py"} for i in range(5)]
        groups = _partition_files(files, 10)
        assert len(groups) == 1
        assert len(groups[0]) == 5

    def test_empty(self) -> None:
        """0 files → empty list."""
        groups = _partition_files([], 10)
        assert groups == []

    def test_preserves_order(self) -> None:
        """File order is preserved within and across groups."""
        files = [{"filename": f"f{i}.py"} for i in range(25)]
        groups = _partition_files(files, 10)
        flattened = [f for g in groups for f in g]
        assert flattened == files


# ---------------------------------------------------------------------------
# Map-reduce: _filter_diff_for_files
# ---------------------------------------------------------------------------


class TestFilterDiffForFiles:
    """Tests for the _filter_diff_for_files diff parser."""

    def test_matching(self) -> None:
        """Matching filenames are kept."""
        diff = (
            "diff --git a/foo.py b/foo.py\n"
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1,3 +1,3 @@\n"
            "-old\n"
            "+new\n"
            "diff --git a/bar.py b/bar.py\n"
            "--- a/bar.py\n"
            "+++ b/bar.py\n"
            "@@ -1 +1 @@\n"
            "+bar\n"
        )
        result = _filter_diff_for_files(diff, {"foo.py"})
        assert "foo.py" in result
        assert "bar.py" not in result

    def test_no_match(self) -> None:
        """No matching filenames → empty string."""
        diff = "diff --git a/foo.py b/foo.py\n+content\n"
        result = _filter_diff_for_files(diff, {"other.py"})
        assert result == ""

    def test_empty_diff(self) -> None:
        """Empty diff → empty string."""
        assert _filter_diff_for_files("", {"foo.py"}) == ""

    def test_empty_filenames(self) -> None:
        """Empty filenames set → empty string."""
        diff = "diff --git a/foo.py b/foo.py\n+content\n"
        assert _filter_diff_for_files(diff, set()) == ""

    def test_partial_match(self) -> None:
        """Multiple sections, only some match."""
        diff = (
            "diff --git a/a.py b/a.py\n+a\n"
            "diff --git a/b.py b/b.py\n+b\n"
            "diff --git a/c.py b/c.py\n+c\n"
        )
        result = _filter_diff_for_files(diff, {"a.py", "c.py"})
        assert "a.py" in result
        assert "c.py" in result
        assert "diff --git a/b.py" not in result


# ---------------------------------------------------------------------------
# Map-reduce: _aggregate_usage
# ---------------------------------------------------------------------------


class TestAggregateUsage:
    """Tests for the _aggregate_usage token summing function."""

    def test_sums_tokens(self, map_reduce_partial_results: list[ReviewResult]) -> None:
        """Token counts are summed across all results."""
        reduce_result = ReviewResult(
            ripeness=Ripeness.ripe,
            summary="Merged.",
            walkthrough="## All\n\nFull walkthrough.",
            findings=[],
            model="claude-sonnet-4-6",
            usage={"input_tokens": 500, "output_tokens": 100},
        )
        totals = _aggregate_usage(map_reduce_partial_results, reduce_result)
        # partials: 1000+2000+3000 = 6000 input, 200+400+600 = 1200 output
        # + reduce: 500 input, 100 output
        assert totals["input_tokens"] == 6500
        assert totals["output_tokens"] == 1300

    def test_handles_cache_fields(self) -> None:
        """Cache fields are summed when present."""
        r1 = ReviewResult(
            ripeness=Ripeness.ripe,
            summary="P1.",
            walkthrough="## W1",
            findings=[],
            model="m",
            usage={
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_creation_input_tokens": 10,
                "cache_read_input_tokens": 20,
            },
        )
        r2 = ReviewResult(
            ripeness=Ripeness.ripe,
            summary="Reduce.",
            walkthrough="## W2",
            findings=[],
            model="m",
            usage={
                "input_tokens": 200,
                "output_tokens": 60,
                "cache_creation_input_tokens": 5,
            },
        )
        totals = _aggregate_usage([r1], r2)
        assert totals["input_tokens"] == 300
        assert totals["output_tokens"] == 110
        assert totals["cache_creation_input_tokens"] == 15
        assert totals["cache_read_input_tokens"] == 20


# ---------------------------------------------------------------------------
# Map-reduce: integration
# ---------------------------------------------------------------------------


class TestMapReduceIntegration:
    """Integration tests for the map-reduce review pipeline."""

    @patch("lychee.review.build_context")
    def test_full_pipeline(
        self,
        mock_build_context: MagicMock,
        review_context_large: ReviewContext,
        mock_github_client: MagicMock,
        mock_claude_client: MagicMock,
        default_config: LycheeConfig,
    ) -> None:
        """Large PR triggers map-reduce pipeline and returns a valid ReviewResult."""
        mock_build_context.return_value = review_context_large

        result = run_review(
            "owner/repo#999", default_config, mock_github_client, mock_claude_client
        )

        assert isinstance(result, ReviewResult)

    @patch("lychee.review.build_context")
    def test_single_pass_unchanged(
        self,
        mock_build_context: MagicMock,
        review_context_simple: ReviewContext,
        mock_github_client: MagicMock,
        mock_claude_client: MagicMock,
        default_config: LycheeConfig,
    ) -> None:
        """Small PR still uses single-pass path (1 claude call)."""
        mock_build_context.return_value = review_context_simple

        result = run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

        assert isinstance(result, ReviewResult)
        # Single-pass: exactly 1 call to claude_client.review
        assert mock_claude_client.review.call_count == 1

    @patch("lychee.review.build_context")
    def test_call_counts(
        self,
        mock_build_context: MagicMock,
        review_context_large: ReviewContext,
        mock_github_client: MagicMock,
        mock_claude_client: MagicMock,
        default_config: LycheeConfig,
    ) -> None:
        """Map-reduce makes N map calls + 1 reduce call."""
        mock_build_context.return_value = review_context_large

        run_review("owner/repo#999", default_config, mock_github_client, mock_claude_client)

        # 62 files / 10 per group = 7 groups → 7 map + 1 reduce = 8 calls
        expected_groups = (
            len(review_context_large.changed_files) + _MAP_GROUP_SIZE - 1
        ) // _MAP_GROUP_SIZE
        assert mock_claude_client.review.call_count == expected_groups + 1

    @patch("lychee.review.build_context")
    def test_usage_aggregation(
        self,
        mock_build_context: MagicMock,
        review_context_large: ReviewContext,
        mock_github_client: MagicMock,
        default_config: LycheeConfig,
    ) -> None:
        """Usage tokens are aggregated across all map and reduce calls."""
        mock_build_context.return_value = review_context_large

        call_count = [0]

        def make_result(*args: Any, **kwargs: Any) -> ReviewResult:
            call_count[0] += 1
            return ReviewResult(
                ripeness=Ripeness.ripe,
                summary=f"Result {call_count[0]}.",
                walkthrough=f"## Walk {call_count[0]}",
                findings=[],
                model="claude-sonnet-4-6",
                usage={"input_tokens": 100, "output_tokens": 50},
            )

        claude_mock = MagicMock()
        claude_mock.review.side_effect = make_result

        result = run_review("owner/repo#999", default_config, mock_github_client, claude_mock)

        total_calls = claude_mock.review.call_count
        assert result.usage["input_tokens"] == 100 * total_calls
        assert result.usage["output_tokens"] == 50 * total_calls

    @patch("lychee.review.build_context")
    def test_model_selection(
        self,
        mock_build_context: MagicMock,
        review_context_large: ReviewContext,
        mock_github_client: MagicMock,
        mock_claude_client: MagicMock,
        default_config: LycheeConfig,
    ) -> None:
        """Map-reduce calls use the same model_override as single-pass would."""
        mock_build_context.return_value = review_context_large

        run_review("owner/repo#999", default_config, mock_github_client, mock_claude_client)

        for call in mock_claude_client.review.call_args_list:
            assert call.kwargs["model_override"] == default_config.model.default


# ---------------------------------------------------------------------------
# Map-reduce: error handling
# ---------------------------------------------------------------------------


class TestMapReduceErrorHandling:
    """Tests for map-reduce error handling paths."""

    @patch("lychee.review.build_context")
    def test_all_fail_raises(
        self,
        mock_build_context: MagicMock,
        review_context_large: ReviewContext,
        mock_github_client: MagicMock,
        default_config: LycheeConfig,
    ) -> None:
        """When all map groups fail, ClaudeReviewError is raised."""
        mock_build_context.return_value = review_context_large
        claude_mock = MagicMock()
        claude_mock.review.side_effect = ClaudeReviewError("API error")

        with pytest.raises(ClaudeReviewError, match="Map phase failed"):
            run_review("owner/repo#999", default_config, mock_github_client, claude_mock)

    @patch("lychee.review.build_context")
    def test_partial_failure_proceeds(
        self,
        mock_build_context: MagicMock,
        review_context_large: ReviewContext,
        mock_github_client: MagicMock,
        default_config: LycheeConfig,
    ) -> None:
        """When some map groups fail, the pipeline continues with successful partials."""
        mock_build_context.return_value = review_context_large
        claude_mock = MagicMock()

        call_idx = [0]

        def side_effect(*args: Any, **kwargs: Any) -> ReviewResult:
            call_idx[0] += 1
            # Fail every other map call
            if call_idx[0] % 2 == 0 and call_idx[0] <= 7:
                raise ClaudeReviewError("Intermittent failure")
            return ReviewResult(
                ripeness=Ripeness.ripe,
                summary=f"Result {call_idx[0]}.",
                walkthrough=f"## Walk {call_idx[0]}",
                findings=[],
                model="claude-sonnet-4-6",
                usage={"input_tokens": 100, "output_tokens": 50},
            )

        claude_mock.review.side_effect = side_effect

        result = run_review("owner/repo#999", default_config, mock_github_client, claude_mock)
        assert isinstance(result, ReviewResult)

    @patch("lychee.review.build_context")
    def test_reduce_failure_raises(
        self,
        mock_build_context: MagicMock,
        review_context_large: ReviewContext,
        mock_github_client: MagicMock,
        default_config: LycheeConfig,
    ) -> None:
        """When the reduce phase fails, the error propagates."""
        mock_build_context.return_value = review_context_large
        claude_mock = MagicMock()

        num_groups = (
            len(review_context_large.changed_files) + _MAP_GROUP_SIZE - 1
        ) // _MAP_GROUP_SIZE
        call_idx = [0]

        def side_effect(*args: Any, **kwargs: Any) -> ReviewResult:
            call_idx[0] += 1
            if call_idx[0] > num_groups:
                raise ClaudeReviewError("Reduce failed")
            return ReviewResult(
                ripeness=Ripeness.ripe,
                summary=f"Partial {call_idx[0]}.",
                walkthrough=f"## Walk {call_idx[0]}",
                findings=[],
                model="claude-sonnet-4-6",
                usage={"input_tokens": 100, "output_tokens": 50},
            )

        claude_mock.review.side_effect = side_effect

        with pytest.raises(ClaudeReviewError, match="Reduce failed"):
            run_review("owner/repo#999", default_config, mock_github_client, claude_mock)


# ---------------------------------------------------------------------------
# Map-reduce: acceptance
# ---------------------------------------------------------------------------


class TestMapReduceAcceptance:
    """Acceptance tests for map-reduce review pipeline."""

    @patch("lychee.review.build_context")
    def test_large_pr_valid_result(
        self,
        mock_build_context: MagicMock,
        review_context_large: ReviewContext,
        mock_github_client: MagicMock,
        mock_claude_client: MagicMock,
        default_config: LycheeConfig,
    ) -> None:
        """A large PR produces a valid ReviewResult via map-reduce."""
        mock_build_context.return_value = review_context_large

        result = run_review(
            "owner/repo#999", default_config, mock_github_client, mock_claude_client
        )

        assert isinstance(result, ReviewResult)
        assert result.ripeness is not None
        assert result.summary
        assert result.model

    @patch("lychee.review.build_context")
    def test_small_pr_bypasses(
        self,
        mock_build_context: MagicMock,
        review_context_simple: ReviewContext,
        mock_github_client: MagicMock,
        mock_claude_client: MagicMock,
        default_config: LycheeConfig,
    ) -> None:
        """A small PR bypasses map-reduce and uses single-pass."""
        mock_build_context.return_value = review_context_simple

        result = run_review("owner/repo#42", default_config, mock_github_client, mock_claude_client)

        assert isinstance(result, ReviewResult)
        assert mock_claude_client.review.call_count == 1


# ---------------------------------------------------------------------------
# Map-reduce: regression
# ---------------------------------------------------------------------------


class TestMapReduceRegression:
    """Regression tests ensuring existing behavior is preserved."""

    def test_dry_run_unchanged(self, default_config: LycheeConfig) -> None:
        """run_review_dry() still works after map-reduce was added."""
        result = run_review_dry(PR_SIMPLE_FIXTURE, default_config)
        assert isinstance(result, str)
        assert REVIEW_MARKER in result

    @patch("lychee.review.build_messages")
    @patch("lychee.review.build_system_prompt_blocks")
    @patch("lychee.review.build_context")
    def test_single_pass_shape_unchanged(
        self,
        mock_build_context: MagicMock,
        mock_build_system_prompt_blocks: MagicMock,
        mock_build_messages: MagicMock,
        mock_github_client: MagicMock,
        mock_claude_client: MagicMock,
        review_context_simple: ReviewContext,
        default_config: LycheeConfig,
    ) -> None:
        """Single-pass ReviewResult shape is unchanged after map-reduce addition."""
        mock_build_context.return_value = review_context_simple
        mock_build_system_prompt_blocks.return_value = [
            {"type": "text", "text": "prompt", "cache_control": {"type": "ephemeral"}}
        ]
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


# ---------------------------------------------------------------------------
# Budget cap tests
# ---------------------------------------------------------------------------


class TestBudgetCapSinglePass:
    """Tests for budget checking in single-pass reviews."""

    @patch("lychee.review.build_messages")
    @patch("lychee.review.build_system_prompt_blocks")
    @patch("lychee.review.build_context")
    def test_run_review_budget_check_single_pass(
        self,
        mock_build_context: MagicMock,
        mock_build_system_prompt_blocks: MagicMock,
        mock_build_messages: MagicMock,
        mock_github_client: MagicMock,
        review_context_simple: ReviewContext,
    ) -> None:
        """A single-pass review that exceeds budget raises BudgetExceededError."""
        mock_build_context.return_value = review_context_simple
        mock_build_system_prompt_blocks.return_value = [
            {"type": "text", "text": "prompt", "cache_control": {"type": "ephemeral"}}
        ]
        mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

        # 10k input + 5k output on Sonnet = ~$0.105
        claude_mock = MagicMock()
        claude_mock.review.return_value = ReviewResult(
            ripeness=Ripeness.ripe,
            summary="Review done.",
            walkthrough="## Walk",
            findings=[],
            model="claude-sonnet-4-6",
            usage={"input_tokens": 10_000, "output_tokens": 5_000},
        )

        # Set budget cap very low so it will be exceeded
        config = LycheeConfig(review={"budget_cap_usd": 0.001})  # type: ignore[arg-type]

        with pytest.raises(BudgetExceededError):
            run_review("owner/repo#42", config, mock_github_client, claude_mock)

    @patch("lychee.review.build_messages")
    @patch("lychee.review.build_system_prompt_blocks")
    @patch("lychee.review.build_context")
    def test_run_review_budget_check_within(
        self,
        mock_build_context: MagicMock,
        mock_build_system_prompt_blocks: MagicMock,
        mock_build_messages: MagicMock,
        mock_github_client: MagicMock,
        review_context_simple: ReviewContext,
    ) -> None:
        """A single-pass review within budget completes normally."""
        mock_build_context.return_value = review_context_simple
        mock_build_system_prompt_blocks.return_value = [
            {"type": "text", "text": "prompt", "cache_control": {"type": "ephemeral"}}
        ]
        mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

        claude_mock = MagicMock()
        claude_mock.review.return_value = ReviewResult(
            ripeness=Ripeness.ripe,
            summary="Review done.",
            walkthrough="## Walk",
            findings=[],
            model="claude-sonnet-4-6",
            usage={"input_tokens": 1000, "output_tokens": 500},
        )

        # Cost ~$0.0105, budget cap $10 — well within
        config = LycheeConfig(review={"budget_cap_usd": 10.0})  # type: ignore[arg-type]

        result = run_review("owner/repo#42", config, mock_github_client, claude_mock)
        assert isinstance(result, ReviewResult)

    @patch("lychee.review.build_messages")
    @patch("lychee.review.build_system_prompt_blocks")
    @patch("lychee.review.build_context")
    def test_run_review_no_budget_cap_unchanged(
        self,
        mock_build_context: MagicMock,
        mock_build_system_prompt_blocks: MagicMock,
        mock_build_messages: MagicMock,
        mock_github_client: MagicMock,
        mock_claude_client: MagicMock,
        review_context_simple: ReviewContext,
    ) -> None:
        """With no budget cap (default), review behaviour is unchanged."""
        mock_build_context.return_value = review_context_simple
        mock_build_system_prompt_blocks.return_value = [
            {"type": "text", "text": "prompt", "cache_control": {"type": "ephemeral"}}
        ]
        mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

        config = LycheeConfig()  # budget_cap_usd is None by default

        result = run_review("owner/repo#42", config, mock_github_client, mock_claude_client)
        assert isinstance(result, ReviewResult)


class TestBudgetCapMapReduce:
    """Tests for budget checking in map-reduce reviews."""

    @patch("lychee.review.build_context")
    def test_map_reduce_budget_exceeded_mid_review(
        self,
        mock_build_context: MagicMock,
        review_context_large: ReviewContext,
        mock_github_client: MagicMock,
    ) -> None:
        """Budget exceeded during map phase raises BudgetExceededError."""
        mock_build_context.return_value = review_context_large

        claude_mock = MagicMock()
        claude_mock.review.return_value = ReviewResult(
            ripeness=Ripeness.ripe,
            summary="Partial.",
            walkthrough="## Walk",
            findings=[],
            model="claude-sonnet-4-6",
            usage={"input_tokens": 50_000, "output_tokens": 10_000},
        )

        # Each call costs ~$0.30. With 7+ map groups, total will far exceed $0.01
        config = LycheeConfig(review={"budget_cap_usd": 0.01})  # type: ignore[arg-type]

        with pytest.raises(BudgetExceededError):
            run_review("owner/repo#999", config, mock_github_client, claude_mock)
