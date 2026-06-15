"""Shared pytest fixtures and configuration for the lychee test suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, create_autospec

import pytest

from lychee.context import ReviewContext
from lychee.github_client import GitHubClient
from lychee.models import (
    Category,
    Finding,
    ReviewResult,
    Ripeness,
    Severity,
)

FIXTURES_DIR: Path = Path(__file__).parent / "fixtures"


@pytest.fixture()
def ripe_review_result() -> ReviewResult:
    """Deterministic ripe ReviewResult loaded from the ripe fixture file."""
    data: dict[str, Any] = json.loads(
        (FIXTURES_DIR / "review_result_ripe.json").read_text(encoding="utf-8")
    )
    return ReviewResult.model_validate(data)


@pytest.fixture()
def unripe_review_result() -> ReviewResult:
    """Deterministic unripe ReviewResult loaded from the unripe fixture file."""
    data: dict[str, Any] = json.loads(
        (FIXTURES_DIR / "review_result_unripe.json").read_text(encoding="utf-8")
    )
    return ReviewResult.model_validate(data)


@pytest.fixture()
def sour_review_result() -> ReviewResult:
    """Deterministic sour ReviewResult loaded from the sour fixture file."""
    data: dict[str, Any] = json.loads(
        (FIXTURES_DIR / "review_result_sour.json").read_text(encoding="utf-8")
    )
    return ReviewResult.model_validate(data)


@pytest.fixture()
def no_findings_review_result() -> ReviewResult:
    """Deterministic ripe ReviewResult with zero findings."""
    return ReviewResult(
        ripeness=Ripeness.ripe,
        summary="Clean PR with no issues found.",
        walkthrough="## Changes\n\nMinor formatting update to README.",
        findings=[],
        model="claude-sonnet-4-6",
        usage={"input_tokens": 500, "output_tokens": 80},
    )


@pytest.fixture()
def pr_simple_payload() -> dict[str, Any]:
    """Parsed pr_simple.json as a Python dict."""
    return json.loads(  # type: ignore[no-any-return]
        (FIXTURES_DIR / "pr_simple.json").read_text(encoding="utf-8")
    )


@pytest.fixture()
def pr_large_payload() -> dict[str, Any]:
    """Parsed pr_large.json as a Python dict."""
    return json.loads(  # type: ignore[no-any-return]
        (FIXTURES_DIR / "pr_large.json").read_text(encoding="utf-8")
    )


@pytest.fixture()
def diff_simple() -> str:
    """Contents of diff_simple.txt as a string."""
    return (FIXTURES_DIR / "diff_simple.txt").read_text(encoding="utf-8")


@pytest.fixture()
def diff_large() -> str:
    """Contents of diff_large.txt as a string."""
    return (FIXTURES_DIR / "diff_large.txt").read_text(encoding="utf-8")


@pytest.fixture()
def mock_github_client() -> MagicMock:
    """Auto-specced MagicMock for GitHubClient with sensible return values."""
    mock: MagicMock = create_autospec(GitHubClient, instance=True)

    # Configure a mock PR object
    mock_pr = MagicMock()
    mock_pr.number = 1
    mock_pr.title = "mock-pr"
    mock_pr.body = "mock body"
    mock_pr.user.login = "mock-user"
    mock_pr.base.ref = "main"
    mock_pr.base.repo.full_name = "owner/repo"
    mock_pr.head.ref = "feat/mock"
    mock_pr.head.sha = "abc123"
    mock.get_pull_request.return_value = mock_pr

    mock.get_diff.return_value = "diff --git a/f.py b/f.py\n"
    mock.get_changed_files.return_value = []
    mock.get_commit_messages.return_value = ["initial commit"]
    mock.get_conventions_file.return_value = None
    return mock


@pytest.fixture()
def mock_claude_client() -> MagicMock:
    """MagicMock standing in for ClaudeClient (no spec, stub only)."""
    mock = MagicMock()
    mock.review.return_value = ReviewResult(
        ripeness=Ripeness.ripe,
        summary="Mock review summary.",
        walkthrough="## Mock\n\nNo real changes.",
        findings=[
            Finding(
                file="mock.py",
                line=1,
                severity=Severity.info,
                category=Category.other,
                message="Mock finding.",
            ),
        ],
        model="mock-model",
        usage={"input_tokens": 0, "output_tokens": 0},
    )
    return mock


@pytest.fixture()
def review_context_simple() -> ReviewContext:
    """A simple ReviewContext fixture for testing downstream consumers."""
    return ReviewContext(
        pr_number=42,
        pr_title="Add utility functions",
        pr_body="This PR adds utility functions.",
        pr_author="octocat",
        base_ref="main",
        head_ref="feat/utils",
        head_sha="abc123def456",
        repo_full_name="owner/repo",
        diff="diff --git a/f.py b/f.py\n+hello\n",
        changed_files=[
            {
                "filename": "src/utils.py",
                "status": "added",
                "additions": 10,
                "deletions": 0,
                "patch": "@@ -0,0 +1,10 @@\n+code here",
                "content_at_head": "# utils\ndef helper(): pass\n",
                "previous_filename": None,
            }
        ],
        commit_messages=["Add utility functions"],
        conventions=None,
    )


@pytest.fixture()
def review_context_large() -> ReviewContext:
    """A large ReviewContext with 62 programmatically-generated files for map-reduce tests."""
    changed_files: list[dict[str, Any]] = []
    diff_lines: list[str] = []
    for i in range(1, 63):
        filename = f"src/module_{i:02d}.py"
        content = f"# module {i}\ndef func_{i}(): pass\n"
        changed_files.append(
            {
                "filename": filename,
                "status": "modified" if i % 2 == 0 else "added",
                "additions": 5,
                "deletions": 2 if i % 2 == 0 else 0,
                "patch": f"@@ -1,3 +1,5 @@\n+# module {i}",
                "content_at_head": content,
                "previous_filename": None,
            }
        )
        diff_lines.append(
            f"diff --git a/{filename} b/{filename}\n"
            f"--- a/{filename}\n"
            f"+++ b/{filename}\n"
            f"@@ -1,3 +1,5 @@\n"
            f"+# module {i}\n"
            f"+def func_{i}(): pass\n"
        )
    return ReviewContext(
        pr_number=999,
        pr_title="Large refactor: migrate to v2 API",
        pr_body="This PR migrates all modules to the v2 API surface.",
        pr_author="dev-lead",
        base_ref="main",
        head_ref="feat/v2-migration",
        head_sha="aaa111bbb222",
        repo_full_name="owner/repo",
        diff="".join(diff_lines),
        changed_files=changed_files,
        commit_messages=["Migrate to v2 API", "Fix lint", "Add missing tests"],
        conventions=None,
    )


@pytest.fixture()
def map_reduce_partial_results() -> list[ReviewResult]:
    """List of 3 ReviewResults simulating map-phase output."""
    return [
        ReviewResult(
            ripeness=Ripeness.ripe,
            summary=f"Partial review {i}: changes look good.",
            walkthrough=f"## Group {i}\n\nFiles reviewed in group {i}.",
            findings=[
                Finding(
                    file=f"src/module_{i * 10 + 1:02d}.py",
                    line=5,
                    severity=Severity.minor,
                    category=Category.style,
                    message=f"Consider renaming func_{i * 10 + 1} for clarity.",
                )
            ],
            model="claude-sonnet-4-6",
            usage={"input_tokens": 1000 * i, "output_tokens": 200 * i},
        )
        for i in range(1, 4)
    ]


@pytest.fixture()
def review_context_minimal() -> ReviewContext:
    """A minimal ReviewContext with empty changed files and no conventions."""
    return ReviewContext(
        pr_number=1,
        pr_title="Empty PR",
        pr_body=None,
        pr_author="bot",
        base_ref="main",
        head_ref="fix/empty",
        head_sha="000000",
        repo_full_name="owner/repo",
        diff="",
        changed_files=[],
        commit_messages=[],
        conventions=None,
    )
