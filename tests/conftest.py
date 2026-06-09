"""Shared pytest fixtures and configuration for the lychee test suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

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
    """MagicMock standing in for GitHubClient (no spec, stub only)."""
    mock = MagicMock()
    mock.get_pull_request.return_value = {
        "number": 1,
        "title": "mock-pr",
        "state": "open",
    }
    mock.get_diff.return_value = "diff --git a/f.py b/f.py\n"
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
