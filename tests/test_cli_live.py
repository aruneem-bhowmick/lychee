"""Tests for the live review CLI path (lychee review --pr).

Covers integration tests for the --pr and --post/--no-post options,
system tests verifying the dry-run path is unaffected, smoke tests for
CLI help output, and regression tests for dry-run output stability.

Framework: pytest, click.testing.CliRunner, unittest.mock.patch.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from lychee.__main__ import cli
from lychee.models import (
    Category,
    Finding,
    ReviewResult,
    Ripeness,
    Severity,
)
from lychee.render import REVIEW_MARKER

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PR_SIMPLE_FIXTURE = FIXTURES_DIR / "pr_simple.json"


def _mock_review_result() -> ReviewResult:
    """Create a minimal ReviewResult for mocking run_review return values."""
    return ReviewResult(
        ripeness=Ripeness.ripe,
        summary="Test summary.",
        walkthrough="## Test\n\nNo changes.",
        findings=[
            Finding(
                file="test.py",
                line=1,
                severity=Severity.info,
                category=Category.other,
                message="Test finding.",
            ),
        ],
        model="claude-sonnet-4-6",
        usage={"input_tokens": 100, "output_tokens": 50},
    )


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestCLILiveIntegration:
    """Integration tests for the live review CLI path."""

    @patch("lychee.__main__.SummaryPoster")
    @patch("lychee.__main__.render_comment")
    @patch("lychee.__main__.run_review")
    @patch("lychee.__main__.ClaudeClient")
    @patch("lychee.__main__.GitHubClient")
    @patch("lychee.__main__.load_config")
    def test_cli_live_review_no_post(
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_render: MagicMock,
        mock_poster_cls: MagicMock,
    ) -> None:
        """--pr with --no-post prints the comment to stdout and does not call poster."""
        mock_review.return_value = _mock_review_result()
        mock_render.return_value = "# Rendered comment for stdout"

        runner = CliRunner(
            env={
                "GITHUB_TOKEN": "ghp_test_token",
                "ANTHROPIC_API_KEY": "sk-ant-test-key",
            }
        )
        result = runner.invoke(cli, ["review", "--pr", "owner/repo#1", "--no-post"])

        assert result.exit_code == 0
        assert "# Rendered comment for stdout" in result.output
        mock_poster_cls.return_value.post.assert_not_called()

    @patch("lychee.__main__.SummaryPoster")
    @patch("lychee.__main__.render_comment")
    @patch("lychee.__main__.run_review")
    @patch("lychee.__main__.ClaudeClient")
    @patch("lychee.__main__.GitHubClient")
    @patch("lychee.__main__.load_config")
    def test_cli_live_review_with_post(
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_render: MagicMock,
        mock_poster_cls: MagicMock,
    ) -> None:
        """--pr with default --post calls poster.post() and echoes confirmation."""
        mock_review.return_value = _mock_review_result()
        mock_render.return_value = "# Posted comment"

        runner = CliRunner(
            env={
                "GITHUB_TOKEN": "ghp_test_token",
                "ANTHROPIC_API_KEY": "sk-ant-test-key",
            }
        )
        result = runner.invoke(cli, ["review", "--pr", "owner/repo#1"])

        assert result.exit_code == 0
        assert "Review posted for owner/repo#1" in result.output
        mock_poster_cls.return_value.post.assert_called_once()

    def test_cli_live_review_missing_github_token(self) -> None:
        """--pr without GITHUB_TOKEN exits non-zero with a usage error."""
        runner = CliRunner(
            env={
                "ANTHROPIC_API_KEY": "sk-ant-test-key",
            }
        )
        result = runner.invoke(cli, ["review", "--pr", "owner/repo#1"])

        assert result.exit_code != 0
        assert "GITHUB_TOKEN" in result.output

    def test_cli_live_review_missing_anthropic_key(self) -> None:
        """--pr without ANTHROPIC_API_KEY exits non-zero with a usage error."""
        runner = CliRunner(
            env={
                "GITHUB_TOKEN": "ghp_test_token",
            }
        )
        result = runner.invoke(cli, ["review", "--pr", "owner/repo#1"])

        assert result.exit_code != 0
        assert "ANTHROPIC_API_KEY" in result.output

    def test_cli_no_args_exits_non_zero(self) -> None:
        """Invoking review without --dry-run or --pr exits non-zero."""
        runner = CliRunner()
        result = runner.invoke(cli, ["review"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# System tests
# ---------------------------------------------------------------------------


class TestSystemCLI:
    """System tests verifying the dry-run path is unaffected by live path additions."""

    def test_system_cli_dry_run_unaffected(self) -> None:
        """Dry-run path still works after live path additions."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["review", "--dry-run", "--fixture", str(PR_SIMPLE_FIXTURE)],
        )
        assert result.exit_code == 0
        assert REVIEW_MARKER in result.output
        assert "Reviewed to the core by Lychee" in result.output


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_cli_help_includes_pr_option() -> None:
    """'lychee review --help' output includes the --pr option."""
    runner = CliRunner()
    result = runner.invoke(cli, ["review", "--help"])
    assert result.exit_code == 0
    assert "--pr" in result.output


def test_cli_help_includes_post_option() -> None:
    """'lychee review --help' output includes the --post/--no-post option."""
    runner = CliRunner()
    result = runner.invoke(cli, ["review", "--help"])
    assert result.exit_code == 0
    assert "--post" in result.output
    assert "--no-post" in result.output


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def test_cli_dry_run_regression() -> None:
    """Dry-run output remains stable: contains all expected sections.

    This test guards against regressions when modifying the CLI: the dry-run
    path must continue to produce a full review comment with all sections.
    """
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["review", "--dry-run", "--fixture", str(PR_SIMPLE_FIXTURE)],
    )
    assert result.exit_code == 0
    # All five comment sections must be present
    assert REVIEW_MARKER in result.output  # Header marker
    assert "Nectar" in result.output  # Summary section
    assert "The Peel" in result.output  # Walkthrough section
    assert "Pits" in result.output  # Findings section
    assert "Reviewed to the core by Lychee" in result.output  # Footer
