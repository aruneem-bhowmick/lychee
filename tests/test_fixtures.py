"""Fixture loading, validation, and mock determinism tests.

Verifies that all shared fixtures load correctly, produce valid domain
objects, and that client mocks behave deterministically across invocations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from lychee.github_client import PullRequestRef
from lychee.models import Finding, ReviewResult, Ripeness

FIXTURES_DIR: Path = Path(__file__).parent / "fixtures"

EXPECTED_FIXTURE_FILES: list[str] = [
    "pr_simple.json",
    "pr_large.json",
    "diff_simple.txt",
    "diff_large.txt",
    "review_result_ripe.json",
    "review_result_unripe.json",
    "review_result_sour.json",
]

REVIEW_RESULT_JSON_FILES: list[str] = [
    "review_result_ripe.json",
    "review_result_unripe.json",
    "review_result_sour.json",
]


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_conftest_imports() -> None:
    """All shared fixtures are importable from conftest via pytest collection."""
    import tests.conftest as _conftest

    names = [
        "FIXTURES_DIR",
        "ripe_review_result",
        "unripe_review_result",
        "sour_review_result",
        "no_findings_review_result",
        "pr_simple_payload",
        "pr_large_payload",
        "diff_simple",
        "diff_large",
        "mock_github_client",
        "mock_claude_client",
        "review_context_simple",
        "review_context_minimal",
    ]
    for name in names:
        assert hasattr(_conftest, name), f"conftest missing: {name}"

    assert _conftest.FIXTURES_DIR.is_dir()


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_fixtures_dir_exists() -> None:
    """The tests/fixtures directory exists and is a directory."""
    assert FIXTURES_DIR.exists()
    assert FIXTURES_DIR.is_dir()


def test_all_fixture_files_present() -> None:
    """Every expected fixture file exists in the fixtures directory."""
    for name in EXPECTED_FIXTURE_FILES:
        path = FIXTURES_DIR / name
        assert path.exists(), f"Missing fixture file: {name}"
        assert path.stat().st_size > 0, f"Fixture file is empty: {name}"


def test_review_result_json_fixtures_valid() -> None:
    """All review_result_*.json fixtures parse as valid ReviewResult objects."""
    for name in REVIEW_RESULT_JSON_FILES:
        path = FIXTURES_DIR / name
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        result = ReviewResult.model_validate(data)
        assert isinstance(result, ReviewResult), f"Failed to validate {name}"


# ---------------------------------------------------------------------------
# Unit tests — ripe fixture
# ---------------------------------------------------------------------------


def test_ripe_is_review_result(ripe_review_result: ReviewResult) -> None:
    """ripe_review_result fixture produces a ReviewResult instance."""
    assert isinstance(ripe_review_result, ReviewResult)


def test_ripe_ripeness(ripe_review_result: ReviewResult) -> None:
    """ripe_review_result has ripeness=ripe."""
    assert ripe_review_result.ripeness == Ripeness.ripe


def test_ripe_has_findings(ripe_review_result: ReviewResult) -> None:
    """ripe_review_result has exactly 2 minor findings."""
    assert len(ripe_review_result.findings) == 2
    for finding in ripe_review_result.findings:
        assert finding.severity == "minor"


def test_ripe_round_trip(ripe_review_result: ReviewResult) -> None:
    """ripe_review_result survives a model_dump / model_validate round-trip."""
    dumped: dict[str, Any] = ripe_review_result.model_dump()
    reconstructed = ReviewResult.model_validate(dumped)
    assert reconstructed == ripe_review_result


# ---------------------------------------------------------------------------
# Unit tests — unripe fixture
# ---------------------------------------------------------------------------


def test_unripe_is_review_result(unripe_review_result: ReviewResult) -> None:
    """unripe_review_result fixture produces a ReviewResult instance."""
    assert isinstance(unripe_review_result, ReviewResult)


def test_unripe_ripeness(unripe_review_result: ReviewResult) -> None:
    """unripe_review_result has ripeness=unripe."""
    assert unripe_review_result.ripeness == Ripeness.unripe


def test_unripe_has_major_finding_with_suggestion(
    unripe_review_result: ReviewResult,
) -> None:
    """unripe_review_result has 1 major finding with a non-None suggestion."""
    assert len(unripe_review_result.findings) == 1
    finding: Finding = unripe_review_result.findings[0]
    assert finding.severity == "major"
    assert finding.suggestion is not None


# ---------------------------------------------------------------------------
# Unit tests — sour fixture
# ---------------------------------------------------------------------------


def test_sour_is_review_result(sour_review_result: ReviewResult) -> None:
    """sour_review_result fixture produces a ReviewResult instance."""
    assert isinstance(sour_review_result, ReviewResult)


def test_sour_ripeness(sour_review_result: ReviewResult) -> None:
    """sour_review_result has ripeness=sour."""
    assert sour_review_result.ripeness == Ripeness.sour


def test_sour_finding_counts(sour_review_result: ReviewResult) -> None:
    """sour_review_result has 1 critical and 2 minor findings."""
    critical = [f for f in sour_review_result.findings if f.severity == "critical"]
    minor = [f for f in sour_review_result.findings if f.severity == "minor"]
    assert len(critical) == 1
    assert len(minor) == 2


# ---------------------------------------------------------------------------
# Unit tests — no-findings fixture
# ---------------------------------------------------------------------------


def test_no_findings_is_review_result(no_findings_review_result: ReviewResult) -> None:
    """no_findings_review_result fixture produces a ReviewResult instance."""
    assert isinstance(no_findings_review_result, ReviewResult)


def test_no_findings_empty_list(no_findings_review_result: ReviewResult) -> None:
    """no_findings_review_result has an empty findings list."""
    assert no_findings_review_result.findings == []


# ---------------------------------------------------------------------------
# Unit tests — PR payload fixtures
# ---------------------------------------------------------------------------


def test_pr_simple_payload_has_required_keys(
    pr_simple_payload: dict[str, Any],
) -> None:
    """pr_simple_payload contains number, title, files, state, and base.sha."""
    assert "number" in pr_simple_payload
    assert "title" in pr_simple_payload
    assert "files" in pr_simple_payload
    assert "state" in pr_simple_payload
    assert "sha" in pr_simple_payload["base"]


def test_pr_large_payload_file_count(
    pr_large_payload: dict[str, Any],
) -> None:
    """pr_large_payload contains 55 files in the files array."""
    assert len(pr_large_payload["files"]) == 55


def test_pr_large_payload_has_binary_files(
    pr_large_payload: dict[str, Any],
) -> None:
    """pr_large_payload includes files with zero additions (binary files)."""
    binary_files = [
        f for f in pr_large_payload["files"] if f["additions"] == 0 and f["deletions"] == 0
    ]
    assert len(binary_files) == 3


def test_pr_large_payload_has_renamed_files(
    pr_large_payload: dict[str, Any],
) -> None:
    """pr_large_payload includes renamed files with previous_filename."""
    renamed = [f for f in pr_large_payload["files"] if f["status"] == "renamed"]
    assert len(renamed) == 2
    for entry in renamed:
        assert "previous_filename" in entry


# ---------------------------------------------------------------------------
# Unit tests — diff fixtures
# ---------------------------------------------------------------------------


def test_diff_simple_is_string(diff_simple: str) -> None:
    """diff_simple fixture is a non-empty string."""
    assert isinstance(diff_simple, str)
    assert len(diff_simple) > 0


def test_diff_large_is_string(diff_large: str) -> None:
    """diff_large fixture is a non-empty string."""
    assert isinstance(diff_large, str)
    assert len(diff_large) > 0


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_fixtures_load(
    ripe_review_result: ReviewResult,
    unripe_review_result: ReviewResult,
    sour_review_result: ReviewResult,
    no_findings_review_result: ReviewResult,
    pr_simple_payload: dict[str, Any],
    pr_large_payload: dict[str, Any],
    diff_simple: str,
    diff_large: str,
) -> None:
    """All eight data fixtures load without error in a single test."""
    assert ripe_review_result.ripeness == Ripeness.ripe
    assert unripe_review_result.ripeness == Ripeness.unripe
    assert sour_review_result.ripeness == Ripeness.sour
    assert no_findings_review_result.findings == []
    assert pr_simple_payload["number"] == 42
    assert pr_large_payload["changed_files"] == 55
    assert "diff --git" in diff_simple
    assert "diff --git" in diff_large


def test_accept_mocks_deterministic(
    mock_github_client: MagicMock,
    mock_claude_client: MagicMock,
) -> None:
    """Client mocks return identical values across multiple calls."""
    ref = PullRequestRef(owner="owner", repo="repo", number=1)
    first_pr = mock_github_client.get_pull_request(ref)
    second_pr = mock_github_client.get_pull_request(ref)
    assert first_pr == second_pr

    first_review: ReviewResult = mock_claude_client.review()
    second_review: ReviewResult = mock_claude_client.review()
    assert first_review == second_review
    assert first_review.ripeness == Ripeness.ripe


def test_accept_harness_reusable(
    ripe_review_result: ReviewResult,
    mock_claude_client: MagicMock,
) -> None:
    """Fixtures and mocks can be combined in the same test without conflict."""
    mock_result: ReviewResult = mock_claude_client.review()
    assert isinstance(mock_result, ReviewResult)
    assert isinstance(ripe_review_result, ReviewResult)
    # Both are ReviewResult but from different sources.
    assert mock_result.summary != ripe_review_result.summary
