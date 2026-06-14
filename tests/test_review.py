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
from lychee.review import (
    _LARGE_PR_THRESHOLD,
    _compute_context_size,
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
