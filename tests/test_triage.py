"""Tests for the triage pre-pass module.

Covers smoke, unit, integration (mocked API), acceptance, sanity,
regression, and API shape tests for the triage classification system.

Framework: pytest, unittest.mock.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from lychee.config import FeaturesConfig, LycheeConfig
from lychee.context import ReviewContext
from lychee.models import Category, Finding, ReviewResult, Ripeness, Severity
from lychee.triage import (
    _TRIAGE_SYSTEM_PROMPT,
    TriageResult,
    TriageVerdict,
    build_triage_prompt,
    build_triage_tool_schema,
    run_triage,
    run_trivial_review,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def default_config() -> LycheeConfig:
    """Default LycheeConfig with triage_pass enabled."""
    return LycheeConfig(
        features=FeaturesConfig(triage_pass=True),
    )


@pytest.fixture()
def trivial_context() -> ReviewContext:
    """A ReviewContext representing a trivial dependency-bump PR."""
    return ReviewContext(
        pr_number=10,
        pr_title="Bump requests from 2.31.0 to 2.32.0",
        pr_body="Bumps [requests](https://github.com/psf/requests) from 2.31.0 to 2.32.0.",
        pr_author="dependabot[bot]",
        base_ref="main",
        head_ref="dependabot/pip/requests-2.32.0",
        head_sha="abc123",
        repo_full_name="owner/repo",
        diff="diff --git a/requirements.txt b/requirements.txt\n"
        "--- a/requirements.txt\n"
        "+++ b/requirements.txt\n"
        "@@ -1 +1 @@\n"
        "-requests==2.31.0\n"
        "+requests==2.32.0\n",
        changed_files=[
            {
                "filename": "requirements.txt",
                "status": "modified",
                "additions": 1,
                "deletions": 1,
                "patch": "@@ -1 +1 @@\n-requests==2.31.0\n+requests==2.32.0",
                "content_at_head": "requests==2.32.0\n",
                "previous_filename": None,
            }
        ],
        commit_messages=["Bump requests from 2.31.0 to 2.32.0"],
        conventions=None,
    )


@pytest.fixture()
def substantive_context() -> ReviewContext:
    """A ReviewContext representing a substantive feature PR."""
    return ReviewContext(
        pr_number=42,
        pr_title="Add user authentication middleware",
        pr_body="This PR adds JWT-based authentication middleware to the API.",
        pr_author="dev",
        base_ref="main",
        head_ref="feat/auth",
        head_sha="def456",
        repo_full_name="owner/repo",
        diff="diff --git a/src/auth.py b/src/auth.py\n"
        "+import jwt\n"
        "+def authenticate(token): ...\n",
        changed_files=[
            {
                "filename": "src/auth.py",
                "status": "added",
                "additions": 50,
                "deletions": 0,
                "patch": "+import jwt\n+def authenticate(token): ...",
                "content_at_head": "import jwt\ndef authenticate(token): ...\n",
                "previous_filename": None,
            },
            {
                "filename": "src/middleware.py",
                "status": "modified",
                "additions": 20,
                "deletions": 5,
                "patch": "@@ ...",
                "content_at_head": "# middleware\n",
                "previous_filename": None,
            },
        ],
        commit_messages=["Add JWT auth middleware", "Add tests"],
        conventions=None,
    )


def _make_classify_response(verdict: str, reason: str) -> MagicMock:
    """Build a mock Anthropic Message response with a classify_pr tool call."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "classify_pr"
    tool_block.input = {"verdict": verdict, "reason": reason}

    response = MagicMock()
    response.content = [tool_block]
    response.usage.input_tokens = 100
    response.usage.output_tokens = 20
    return response


def _make_mock_claude_client() -> MagicMock:
    """Build a mock ClaudeClient with a mock Anthropic client attached."""
    mock = MagicMock()
    mock._client = MagicMock()
    return mock


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


class TestSmoke:
    """Verify module importability."""

    def test_triage_module_imports(self) -> None:
        """Triage public API is importable from lychee.triage."""
        from lychee.triage import TriageResult, TriageVerdict, run_triage

        assert TriageVerdict is not None
        assert TriageResult is not None
        assert callable(run_triage)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestTriageVerdictUnit:
    """Unit tests for TriageVerdict enum."""

    def test_triage_verdict_values(self) -> None:
        """TriageVerdict has exactly 'trivial' and 'substantive' values."""
        assert TriageVerdict.trivial == "trivial"
        assert TriageVerdict.substantive == "substantive"
        assert set(TriageVerdict) == {TriageVerdict.trivial, TriageVerdict.substantive}


class TestTriageResultUnit:
    """Unit tests for TriageResult."""

    def test_triage_result_is_trivial(self) -> None:
        """TriageResult with 'trivial' verdict has is_trivial == True."""
        result = TriageResult(TriageVerdict.trivial, "Just a typo fix")
        assert result.is_trivial is True
        assert result.verdict == TriageVerdict.trivial
        assert result.reason == "Just a typo fix"

    def test_triage_result_is_substantive(self) -> None:
        """TriageResult with 'substantive' verdict has is_trivial == False."""
        result = TriageResult(TriageVerdict.substantive, "New feature added")
        assert result.is_trivial is False
        assert result.verdict == TriageVerdict.substantive


class TestBuildTriagePromptUnit:
    """Unit tests for build_triage_prompt()."""

    def test_build_triage_prompt_structure(self, trivial_context: ReviewContext) -> None:
        """build_triage_prompt returns (str, list) with expected content."""
        system, messages = build_triage_prompt(trivial_context)

        assert isinstance(system, str)
        assert isinstance(messages, list)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert "classify" in system.lower()
        assert trivial_context.pr_title in messages[0]["content"]

    def test_build_triage_prompt_truncates_diff(self, trivial_context: ReviewContext) -> None:
        """Diff longer than 2000 chars is truncated in the triage message."""
        long_diff = "x" * 3000
        ctx = trivial_context.model_copy(update={"diff": long_diff})

        _, messages = build_triage_prompt(ctx)
        content = messages[0]["content"]

        # The diff section should be truncated
        assert "truncated" in content.lower()
        # The raw diff content should not exceed _MAX_DIFF_CHARS + overhead
        assert long_diff not in content

    def test_build_triage_prompt_truncates_body(self, trivial_context: ReviewContext) -> None:
        """PR body longer than 500 chars is truncated in the triage message."""
        long_body = "y" * 1000
        ctx = trivial_context.model_copy(update={"pr_body": long_body})

        _, messages = build_triage_prompt(ctx)
        content = messages[0]["content"]

        # Truncation indicator
        assert "..." in content
        assert long_body not in content

    def test_triage_prompt_no_file_content(self) -> None:
        """Triage message contains filenames but not file content (lightweight)."""
        ctx = ReviewContext(
            pr_number=1,
            pr_title="Add utils",
            pr_body="Adds utility module.",
            pr_author="dev",
            base_ref="main",
            head_ref="feat/utils",
            head_sha="aaa",
            repo_full_name="owner/repo",
            diff="diff --git a/src/utils.py b/src/utils.py\n+line\n",
            changed_files=[
                {
                    "filename": "src/utils.py",
                    "status": "added",
                    "additions": 10,
                    "deletions": 0,
                    "patch": "@@ +code",
                    "content_at_head": "UNIQUE_FILE_CONTENT_MARKER_XYZ123\n",
                    "previous_filename": None,
                }
            ],
            commit_messages=["Add utils"],
            conventions=None,
        )
        _, messages = build_triage_prompt(ctx)
        content = messages[0]["content"]

        # Should contain the filename
        assert "src/utils.py" in content
        # Should NOT contain the file content (content_at_head)
        assert "UNIQUE_FILE_CONTENT_MARKER_XYZ123" not in content

    def test_build_triage_prompt_empty_body(self) -> None:
        """build_triage_prompt handles None PR body gracefully."""
        ctx = ReviewContext(
            pr_number=1,
            pr_title="Fix typo",
            pr_body=None,
            pr_author="dev",
            base_ref="main",
            head_ref="fix/typo",
            head_sha="aaa",
            repo_full_name="owner/repo",
            diff="diff --git a/f.py b/f.py\n+fix\n",
            changed_files=[
                {
                    "filename": "f.py",
                    "status": "modified",
                    "additions": 1,
                    "deletions": 1,
                    "patch": "+fix",
                    "content_at_head": "fix\n",
                    "previous_filename": None,
                }
            ],
            commit_messages=["Fix typo"],
            conventions=None,
        )

        _, messages = build_triage_prompt(ctx)
        content = messages[0]["content"]

        # Should not contain "PR Body:" since body is None
        assert "PR Body:" not in content
        assert "Fix typo" in content


class TestBuildTriageToolSchemaUnit:
    """Unit tests for build_triage_tool_schema()."""

    def test_build_triage_tool_schema(self) -> None:
        """Schema has name 'classify_pr' with verdict enum and reason."""
        schema = build_triage_tool_schema()

        assert schema["name"] == "classify_pr"
        assert "input_schema" in schema
        props = schema["input_schema"]["properties"]
        assert props["verdict"]["enum"] == ["trivial", "substantive"]
        assert props["reason"]["type"] == "string"
        assert schema["input_schema"]["required"] == ["verdict", "reason"]


# ---------------------------------------------------------------------------
# Integration tests (mocked API)
# ---------------------------------------------------------------------------


class TestRunTriageIntegration:
    """Integration tests for run_triage() with mocked Claude API."""

    def test_run_triage_trivial(
        self,
        trivial_context: ReviewContext,
        default_config: LycheeConfig,
    ) -> None:
        """Mock Claude returning classify_pr with 'trivial'; verify is_trivial."""
        mock_client = _make_mock_claude_client()
        mock_client._client.messages.create.return_value = _make_classify_response(
            "trivial", "Only a dependency bump"
        )

        result = run_triage(trivial_context, mock_client, default_config)

        assert result.is_trivial is True
        assert result.verdict == TriageVerdict.trivial
        assert "dependency" in result.reason.lower()

    def test_run_triage_substantive(
        self,
        substantive_context: ReviewContext,
        default_config: LycheeConfig,
    ) -> None:
        """Mock Claude returning 'substantive'; verify not is_trivial."""
        mock_client = _make_mock_claude_client()
        mock_client._client.messages.create.return_value = _make_classify_response(
            "substantive", "Adds new authentication feature"
        )

        result = run_triage(substantive_context, mock_client, default_config)

        assert result.is_trivial is False
        assert result.verdict == TriageVerdict.substantive

    def test_run_triage_error_defaults_substantive(
        self,
        trivial_context: ReviewContext,
        default_config: LycheeConfig,
    ) -> None:
        """Mock Claude raising an error; verify triage returns substantive (fail-safe)."""
        mock_client = _make_mock_claude_client()
        mock_client._client.messages.create.side_effect = Exception("API timeout")

        result = run_triage(trivial_context, mock_client, default_config)

        assert result.is_trivial is False
        assert result.verdict == TriageVerdict.substantive
        assert "error" in result.reason.lower()

    def test_run_triage_no_tool_call_defaults_substantive(
        self,
        trivial_context: ReviewContext,
        default_config: LycheeConfig,
    ) -> None:
        """When response has no classify_pr tool call, default to substantive."""
        mock_client = _make_mock_claude_client()
        response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        response.content = [text_block]
        mock_client._client.messages.create.return_value = response

        result = run_triage(trivial_context, mock_client, default_config)

        assert result.is_trivial is False
        assert result.verdict == TriageVerdict.substantive

    def test_run_triage_uses_triage_model(
        self,
        trivial_context: ReviewContext,
        default_config: LycheeConfig,
    ) -> None:
        """Verify run_triage calls Claude with the configured triage model."""
        mock_client = _make_mock_claude_client()
        mock_client._client.messages.create.return_value = _make_classify_response(
            "trivial", "Simple change"
        )

        run_triage(trivial_context, mock_client, default_config)

        call_kwargs = mock_client._client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-haiku-4-5-20251001"

    def test_run_triage_uses_tool_choice(
        self,
        trivial_context: ReviewContext,
        default_config: LycheeConfig,
    ) -> None:
        """Verify run_triage forces the classify_pr tool via tool_choice."""
        mock_client = _make_mock_claude_client()
        mock_client._client.messages.create.return_value = _make_classify_response(
            "trivial", "Simple"
        )

        run_triage(trivial_context, mock_client, default_config)

        call_kwargs = mock_client._client.messages.create.call_args
        assert call_kwargs.kwargs["tool_choice"] == {
            "type": "tool",
            "name": "classify_pr",
        }


class TestRunTrivialReviewIntegration:
    """Integration tests for run_trivial_review()."""

    def test_run_trivial_review_returns_review_result(
        self,
        trivial_context: ReviewContext,
        default_config: LycheeConfig,
    ) -> None:
        """Mock Haiku returning submit_review; verify valid ReviewResult."""
        mock_client = MagicMock()
        expected_result = ReviewResult(
            ripeness=Ripeness.ripe,
            summary="Clean dependency bump, no issues.",
            walkthrough="## Changes\n\nUpdated requests version.",
            findings=[],
            model="claude-haiku-4-5-20251001",
            usage={"input_tokens": 200, "output_tokens": 50},
        )
        mock_client.review.return_value = expected_result

        result = run_trivial_review(trivial_context, mock_client, default_config)

        assert isinstance(result, ReviewResult)
        assert result.ripeness == Ripeness.ripe
        assert result.model == "claude-haiku-4-5-20251001"

    def test_run_trivial_review_uses_triage_model(
        self,
        trivial_context: ReviewContext,
        default_config: LycheeConfig,
    ) -> None:
        """Verify run_trivial_review passes the triage model as model_override."""
        mock_client = MagicMock()
        mock_client.review.return_value = ReviewResult(
            ripeness=Ripeness.ripe,
            summary="OK",
            walkthrough="## OK",
            findings=[],
            model="claude-haiku-4-5-20251001",
            usage={"input_tokens": 100, "output_tokens": 30},
        )

        run_trivial_review(trivial_context, mock_client, default_config)

        call_kwargs = mock_client.review.call_args
        assert call_kwargs.kwargs["model_override"] == "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Review integration tests (triage routing in run_review)
# ---------------------------------------------------------------------------


class TestRunReviewWithTriageIntegration:
    """Integration tests for triage routing inside run_review()."""

    @patch("lychee.review.build_messages")
    @patch("lychee.review.build_system_prompt_blocks")
    @patch("lychee.review.build_context")
    @patch("lychee.triage.run_trivial_review")
    @patch("lychee.triage.run_triage")
    def test_run_review_with_triage_trivial(
        self,
        mock_run_triage: MagicMock,
        mock_run_trivial_review: MagicMock,
        mock_build_context: MagicMock,
        mock_build_system_prompt_blocks: MagicMock,
        mock_build_messages: MagicMock,
    ) -> None:
        """Triage enabled; trivial PR; verify Haiku review called, full review skipped."""
        from lychee.review import run_review

        config = LycheeConfig(features=FeaturesConfig(triage_pass=True))
        ctx = ReviewContext(
            pr_number=1,
            pr_title="Fix typo",
            pr_body="typo fix",
            pr_author="dev",
            base_ref="main",
            head_ref="fix/typo",
            head_sha="aaa",
            repo_full_name="owner/repo",
            diff="diff --git a/f.py b/f.py\n+fix\n",
            changed_files=[],
            commit_messages=["Fix typo"],
            conventions=None,
        )
        mock_build_context.return_value = ctx

        mock_run_triage.return_value = TriageResult(TriageVerdict.trivial, "Typo fix only")
        trivial_result = ReviewResult(
            ripeness=Ripeness.ripe,
            summary="Clean typo fix.",
            walkthrough="## Typo\n\nFixed.",
            findings=[],
            model="claude-haiku-4-5-20251001",
            usage={"input_tokens": 100, "output_tokens": 20},
        )
        mock_run_trivial_review.return_value = trivial_result

        mock_github = MagicMock()
        mock_claude = MagicMock()

        result = run_review("owner/repo#1", config, mock_github, mock_claude)

        assert result == trivial_result
        mock_run_triage.assert_called_once()
        mock_run_trivial_review.assert_called_once()
        # Full review (claude_client.review) should NOT have been called
        mock_claude.review.assert_not_called()

    @patch("lychee.review.build_messages")
    @patch("lychee.review.build_system_prompt_blocks")
    @patch("lychee.review.build_context")
    @patch("lychee.triage.run_triage")
    def test_run_review_with_triage_substantive(
        self,
        mock_run_triage: MagicMock,
        mock_build_context: MagicMock,
        mock_build_system_prompt_blocks: MagicMock,
        mock_build_messages: MagicMock,
    ) -> None:
        """Triage enabled; substantive PR; verify full review called."""
        from lychee.review import run_review

        config = LycheeConfig(features=FeaturesConfig(triage_pass=True))
        ctx = ReviewContext(
            pr_number=42,
            pr_title="Add auth",
            pr_body="Auth feature",
            pr_author="dev",
            base_ref="main",
            head_ref="feat/auth",
            head_sha="bbb",
            repo_full_name="owner/repo",
            diff="diff --git a/src/auth.py b/src/auth.py\n+code\n",
            changed_files=[],
            commit_messages=["Add auth"],
            conventions=None,
        )
        mock_build_context.return_value = ctx
        mock_build_system_prompt_blocks.return_value = [
            {"type": "text", "text": "system", "cache_control": {"type": "ephemeral"}}
        ]
        mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

        mock_run_triage.return_value = TriageResult(TriageVerdict.substantive, "New feature")

        full_result = ReviewResult(
            ripeness=Ripeness.unripe,
            summary="Auth needs work.",
            walkthrough="## Auth\n\nReview.",
            findings=[
                Finding(
                    file="src/auth.py",
                    line=10,
                    severity=Severity.major,
                    category=Category.security,
                    message="Missing input validation.",
                )
            ],
            model="claude-sonnet-4-6",
            usage={"input_tokens": 500, "output_tokens": 200},
        )

        mock_github = MagicMock()
        mock_claude = MagicMock()
        mock_claude.review.return_value = full_result

        result = run_review("owner/repo#42", config, mock_github, mock_claude)

        assert result == full_result
        mock_run_triage.assert_called_once()
        mock_claude.review.assert_called_once()

    @patch("lychee.triage.run_triage")
    @patch("lychee.review.build_messages")
    @patch("lychee.review.build_system_prompt_blocks")
    @patch("lychee.review.build_context")
    def test_run_review_without_triage(
        self,
        mock_build_context: MagicMock,
        mock_build_system_prompt_blocks: MagicMock,
        mock_build_messages: MagicMock,
        mock_run_triage: MagicMock,
    ) -> None:
        """Triage disabled; verify triage never called."""
        from lychee.review import run_review

        config = LycheeConfig(features=FeaturesConfig(triage_pass=False))
        ctx = ReviewContext(
            pr_number=1,
            pr_title="Some PR",
            pr_body="body",
            pr_author="dev",
            base_ref="main",
            head_ref="feat/x",
            head_sha="ccc",
            repo_full_name="owner/repo",
            diff="diff --git a/f.py b/f.py\n+code\n",
            changed_files=[],
            commit_messages=["commit"],
            conventions=None,
        )
        mock_build_context.return_value = ctx
        mock_build_system_prompt_blocks.return_value = [
            {"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}
        ]
        mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

        mock_github = MagicMock()
        mock_claude = MagicMock()
        mock_claude.review.return_value = ReviewResult(
            ripeness=Ripeness.ripe,
            summary="OK.",
            walkthrough="## OK",
            findings=[],
            model="claude-sonnet-4-6",
            usage={"input_tokens": 100, "output_tokens": 30},
        )

        result = run_review("owner/repo#1", config, mock_github, mock_claude)

        mock_run_triage.assert_not_called()
        assert result.model == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


class TestAcceptance:
    """Acceptance tests validating the triage routing contracts."""

    def test_accept_trivial_prs_cheap_path(
        self,
        trivial_context: ReviewContext,
        default_config: LycheeConfig,
    ) -> None:
        """A dependency-bump PR classified as trivial uses the triage model only."""
        mock_client = _make_mock_claude_client()
        mock_client._client.messages.create.return_value = _make_classify_response(
            "trivial", "Only bumps a dependency version"
        )

        triage_result = run_triage(trivial_context, mock_client, default_config)
        assert triage_result.is_trivial

        # Verify the triage model was used
        call_kwargs = mock_client._client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == default_config.model.triage

    def test_accept_substantive_prs_escalate(
        self,
        substantive_context: ReviewContext,
        default_config: LycheeConfig,
    ) -> None:
        """A feature PR classified as substantive uses the default/large model."""
        mock_client = _make_mock_claude_client()
        mock_client._client.messages.create.return_value = _make_classify_response(
            "substantive", "Adds authentication feature"
        )

        triage_result = run_triage(substantive_context, mock_client, default_config)
        assert not triage_result.is_trivial

    def test_accept_routing_logged(
        self,
        trivial_context: ReviewContext,
        default_config: LycheeConfig,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Triage verdict and routing decision appear in log output."""
        mock_client = _make_mock_claude_client()
        mock_client._client.messages.create.return_value = _make_classify_response(
            "trivial", "Documentation-only change"
        )

        with caplog.at_level(logging.INFO, logger="lychee.triage"):
            run_triage(trivial_context, mock_client, default_config)

        assert any("trivial" in record.message.lower() for record in caplog.records)
        assert any("verdict" in record.message.lower() for record in caplog.records)


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


class TestSanity:
    """Sanity tests ensuring backward compatibility."""

    @patch("lychee.review.build_messages")
    @patch("lychee.review.build_system_prompt_blocks")
    @patch("lychee.review.build_context")
    def test_review_without_triage_unchanged(
        self,
        mock_build_context: MagicMock,
        mock_build_system_prompt_blocks: MagicMock,
        mock_build_messages: MagicMock,
    ) -> None:
        """With triage_pass=False, run_review() behaves identically to before triage."""
        from lychee.review import run_review

        config = LycheeConfig(features=FeaturesConfig(triage_pass=False))
        ctx = ReviewContext(
            pr_number=1,
            pr_title="Normal PR",
            pr_body="A normal PR",
            pr_author="dev",
            base_ref="main",
            head_ref="feat/normal",
            head_sha="xyz",
            repo_full_name="owner/repo",
            diff="diff --git a/f.py b/f.py\n+line\n",
            changed_files=[],
            commit_messages=["Normal commit"],
            conventions=None,
        )
        mock_build_context.return_value = ctx
        mock_build_system_prompt_blocks.return_value = [
            {"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}
        ]
        mock_build_messages.return_value = [{"role": "user", "content": "msg"}]

        expected = ReviewResult(
            ripeness=Ripeness.ripe,
            summary="All good.",
            walkthrough="## Clean",
            findings=[],
            model="claude-sonnet-4-6",
            usage={"input_tokens": 200, "output_tokens": 50},
        )

        mock_github = MagicMock()
        mock_claude = MagicMock()
        mock_claude.review.return_value = expected

        result = run_review("owner/repo#1", config, mock_github, mock_claude)

        # Result should come from the normal pipeline, not triage
        assert result == expected
        mock_claude.review.assert_called_once()


# ---------------------------------------------------------------------------
# Regression tests (snapshots)
# ---------------------------------------------------------------------------


class TestRegression:
    """Regression/snapshot tests for triage prompts and schemas."""

    def test_triage_prompt_snapshot(self, trivial_context: ReviewContext) -> None:
        """Snapshot of the triage system prompt for a fixed context."""
        system, _messages = build_triage_prompt(trivial_context)

        # The system prompt should match the expected constant
        assert system == _TRIAGE_SYSTEM_PROMPT
        assert "classify" in system.lower()
        assert "trivial" in system
        assert "substantive" in system

    def test_triage_tool_schema_snapshot(self) -> None:
        """Snapshot of the classify_pr tool schema."""
        schema = build_triage_tool_schema()

        expected = {
            "name": "classify_pr",
            "description": "Classify a PR as trivial or substantive.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "verdict": {
                        "type": "string",
                        "enum": ["trivial", "substantive"],
                    },
                    "reason": {
                        "type": "string",
                    },
                },
                "required": ["verdict", "reason"],
            },
        }
        assert schema == expected


# ---------------------------------------------------------------------------
# API shape tests
# ---------------------------------------------------------------------------


class TestAPIShape:
    """Tests verifying the triage API conforms to Anthropic tool-use format."""

    def test_api_triage_tool_schema_shape(self) -> None:
        """classify_pr tool definition matches Anthropic tool-use format."""
        schema = build_triage_tool_schema()

        # Must have name, description, and input_schema at top level
        assert "name" in schema
        assert "description" in schema
        assert "input_schema" in schema
        assert isinstance(schema["name"], str)
        assert isinstance(schema["description"], str)
        assert isinstance(schema["input_schema"], dict)
        assert schema["input_schema"]["type"] == "object"

    def test_api_triage_messages_create_params(
        self,
        trivial_context: ReviewContext,
        default_config: LycheeConfig,
    ) -> None:
        """Verify the triage call uses the correct model and tool_choice."""
        mock_client = _make_mock_claude_client()
        mock_client._client.messages.create.return_value = _make_classify_response(
            "trivial", "Simple"
        )

        run_triage(trivial_context, mock_client, default_config)

        call_kwargs = mock_client._client.messages.create.call_args.kwargs

        # Model should be the triage model (Haiku)
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"

        # tool_choice should force classify_pr
        assert call_kwargs["tool_choice"] == {
            "type": "tool",
            "name": "classify_pr",
        }

        # tools should contain exactly the classify_pr schema
        assert len(call_kwargs["tools"]) == 1
        assert call_kwargs["tools"][0]["name"] == "classify_pr"

        # system should be the triage system prompt
        assert isinstance(call_kwargs["system"], str)
        assert "classify" in call_kwargs["system"].lower()
