"""Tests for lychee.context — ReviewContext model and build_context() orchestration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pydantic
import pytest

from lychee.config import LycheeConfig
from lychee.context import ReviewContext, build_context
from lychee.github_client import ChangedFile, PullRequestRef

# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_context_imports() -> None:
    """ReviewContext and build_context are importable from lychee.context."""

    from lychee import context as mod

    assert hasattr(mod, "ReviewContext")
    assert hasattr(mod, "build_context")
    assert callable(mod.build_context)


# ---------------------------------------------------------------------------
# Unit tests — ReviewContext construction
# ---------------------------------------------------------------------------


def test_review_context_construction() -> None:
    """ReviewContext can be constructed with all required fields."""

    ctx = ReviewContext(
        pr_number=42,
        pr_title="Test PR",
        pr_body="A description",
        pr_author="author",
        base_ref="main",
        head_ref="feat/test",
        head_sha="abc123",
        repo_full_name="owner/repo",
        diff="diff content",
        changed_files=[{"filename": "a.py", "status": "added"}],
        commit_messages=["commit 1"],
        conventions="# rules",
    )
    assert ctx.pr_number == 42
    assert ctx.pr_title == "Test PR"
    assert ctx.conventions == "# rules"


def test_review_context_optional_conventions() -> None:
    """ReviewContext defaults conventions to None."""

    ctx = ReviewContext(
        pr_number=1,
        pr_title="t",
        pr_body=None,
        pr_author="a",
        base_ref="main",
        head_ref="fix",
        head_sha="000",
        repo_full_name="o/r",
        diff="",
        changed_files=[],
        commit_messages=[],
    )
    assert ctx.conventions is None


def test_review_context_frozen() -> None:
    """ReviewContext is immutable after construction."""

    ctx = ReviewContext(
        pr_number=1,
        pr_title="t",
        pr_body=None,
        pr_author="a",
        base_ref="main",
        head_ref="fix",
        head_sha="000",
        repo_full_name="o/r",
        diff="",
        changed_files=[],
        commit_messages=[],
    )
    with pytest.raises(pydantic.ValidationError):
        ctx.pr_number = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_review_context_simple_fixture(review_context_simple: ReviewContext) -> None:
    """review_context_simple fixture produces a valid ReviewContext."""

    assert isinstance(review_context_simple, ReviewContext)
    assert review_context_simple.pr_number == 42
    assert len(review_context_simple.changed_files) == 1


def test_review_context_minimal(review_context_minimal: ReviewContext) -> None:
    """A minimal valid ReviewContext constructs without error."""

    assert isinstance(review_context_minimal, ReviewContext)
    assert review_context_minimal.pr_number == 1
    assert review_context_minimal.changed_files == []
    assert review_context_minimal.conventions is None


# ---------------------------------------------------------------------------
# Helper — mock PR object builder
# ---------------------------------------------------------------------------


def _build_mock_pr(
    number: int = 42,
    title: str = "Test PR",
    body: str | None = "body text",
    login: str = "octocat",
    base_ref: str = "main",
    head_ref: str = "feat/test",
    head_sha: str = "abc123",
    repo_full_name: str = "owner/repo",
) -> MagicMock:
    """Create a mock PullRequest for build_context tests."""
    pr = MagicMock()
    pr.number = number
    pr.title = title
    pr.body = body
    pr.user.login = login
    pr.base.ref = base_ref
    pr.base.repo.full_name = repo_full_name
    pr.head.ref = head_ref
    pr.head.sha = head_sha
    return pr


# ---------------------------------------------------------------------------
# Integration tests — build_context()
# ---------------------------------------------------------------------------


def test_build_context_full() -> None:
    """build_context assembles a full ReviewContext from GitHubClient calls."""

    mock_client = MagicMock()
    mock_pr = _build_mock_pr()
    mock_client.get_pull_request.return_value = mock_pr
    mock_client.get_diff.return_value = "diff --git a/x.py b/x.py\n"
    mock_client.get_changed_files.return_value = [
        ChangedFile(
            filename="x.py",
            status="modified",
            additions=5,
            deletions=2,
            patch="@@ +1 @@",
            content_at_head="new content",
        ),
    ]
    mock_client.get_commit_messages.return_value = ["init", "fix typo"]
    mock_client.get_conventions_file.return_value = "# Style Guide\n"

    config = LycheeConfig(conventions_file="CONVENTIONS.md")
    ref = PullRequestRef.parse("owner/repo#42")

    ctx = build_context(mock_client, ref, config)

    assert isinstance(ctx, ReviewContext)
    assert ctx.pr_number == 42
    assert ctx.pr_title == "Test PR"
    assert ctx.pr_body == "body text"
    assert ctx.pr_author == "octocat"
    assert ctx.base_ref == "main"
    assert ctx.head_ref == "feat/test"
    assert ctx.head_sha == "abc123"
    assert ctx.repo_full_name == "owner/repo"
    assert "diff --git" in ctx.diff
    assert len(ctx.changed_files) == 1
    assert ctx.changed_files[0]["filename"] == "x.py"
    assert ctx.commit_messages == ["init", "fix typo"]
    assert ctx.conventions == "# Style Guide\n"


def test_build_context_no_conventions() -> None:
    """build_context sets conventions=None when no conventions_file is configured."""

    mock_client = MagicMock()
    mock_pr = _build_mock_pr()
    mock_client.get_pull_request.return_value = mock_pr
    mock_client.get_diff.return_value = ""
    mock_client.get_changed_files.return_value = []
    mock_client.get_commit_messages.return_value = []
    mock_client.get_conventions_file.return_value = None

    config = LycheeConfig()  # conventions_file defaults to None
    ref = PullRequestRef.parse("owner/repo#42")

    ctx = build_context(mock_client, ref, config)

    assert ctx.conventions is None
    mock_client.get_conventions_file.assert_called_once_with(
        repo_full_name="owner/repo",
        path=None,
        ref="abc123",
    )


def test_build_context_empty_pr() -> None:
    """build_context handles a PR with no files, no commits, empty diff."""

    mock_client = MagicMock()
    mock_pr = _build_mock_pr(body=None)
    mock_client.get_pull_request.return_value = mock_pr
    mock_client.get_diff.return_value = ""
    mock_client.get_changed_files.return_value = []
    mock_client.get_commit_messages.return_value = []
    mock_client.get_conventions_file.return_value = None

    config = LycheeConfig()
    ref = PullRequestRef.parse("owner/repo#42")

    ctx = build_context(mock_client, ref, config)

    assert ctx.pr_body is None
    assert ctx.diff == ""
    assert ctx.changed_files == []
    assert ctx.commit_messages == []


def test_build_context_passes_config_limits() -> None:
    """build_context forwards max_files, max_file_bytes, and ignore_globs from config."""

    mock_client = MagicMock()
    mock_pr = _build_mock_pr()
    mock_client.get_pull_request.return_value = mock_pr
    mock_client.get_diff.return_value = ""
    mock_client.get_changed_files.return_value = []
    mock_client.get_commit_messages.return_value = []
    mock_client.get_conventions_file.return_value = None

    config = LycheeConfig(
        review={"max_files": 10, "max_file_bytes": 2048, "ignore_globs": ["*.lock"]},  # type: ignore[arg-type]
    )
    ref = PullRequestRef.parse("owner/repo#42")

    build_context(mock_client, ref, config)

    mock_client.get_changed_files.assert_called_once_with(
        mock_pr,
        max_files=10,
        max_file_bytes=2048,
        ignore_globs=["*.lock"],
    )


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_complete_context() -> None:
    """End-to-end: build_context produces a fully populated ReviewContext."""

    mock_client = MagicMock()
    mock_pr = _build_mock_pr(
        number=100,
        title="Big Feature",
        body="Adds a big feature",
        login="dev",
        head_sha="deadbeef",
    )
    mock_client.get_pull_request.return_value = mock_pr
    mock_client.get_diff.return_value = "diff --git a/a.py b/a.py\n+line1\n+line2\n"
    mock_client.get_changed_files.return_value = [
        ChangedFile("a.py", "added", 2, 0, "+line1\n+line2", "line1\nline2\n"),
        ChangedFile("b.py", "modified", 1, 1, "-old\n+new", "new\n"),
    ]
    mock_client.get_commit_messages.return_value = ["feat: add feature", "fix: typo"]
    mock_client.get_conventions_file.return_value = "Follow PEP 8."

    config = LycheeConfig(conventions_file="STYLE.md")
    ref = PullRequestRef.parse("owner/repo#100")

    ctx = build_context(mock_client, ref, config)

    assert ctx.pr_number == 100
    assert ctx.pr_title == "Big Feature"
    assert ctx.pr_author == "dev"
    assert ctx.head_sha == "deadbeef"
    assert len(ctx.changed_files) == 2
    assert ctx.changed_files[0]["filename"] == "a.py"
    assert ctx.changed_files[1]["filename"] == "b.py"
    assert ctx.commit_messages == ["feat: add feature", "fix: typo"]
    assert ctx.conventions == "Follow PEP 8."


def test_accept_respects_max_files() -> None:
    """build_context passes max_files from config to get_changed_files."""

    mock_client = MagicMock()
    mock_pr = _build_mock_pr()
    mock_client.get_pull_request.return_value = mock_pr
    mock_client.get_diff.return_value = ""
    mock_client.get_changed_files.return_value = []
    mock_client.get_commit_messages.return_value = []
    mock_client.get_conventions_file.return_value = None

    config = LycheeConfig(review={"max_files": 5})  # type: ignore[arg-type]
    ref = PullRequestRef.parse("owner/repo#1")

    build_context(mock_client, ref, config)

    _, kwargs = mock_client.get_changed_files.call_args
    assert kwargs["max_files"] == 5


def test_accept_respects_max_file_bytes() -> None:
    """build_context passes max_file_bytes from config to get_changed_files."""

    mock_client = MagicMock()
    mock_pr = _build_mock_pr()
    mock_client.get_pull_request.return_value = mock_pr
    mock_client.get_diff.return_value = ""
    mock_client.get_changed_files.return_value = []
    mock_client.get_commit_messages.return_value = []
    mock_client.get_conventions_file.return_value = None

    config = LycheeConfig(review={"max_file_bytes": 2048})  # type: ignore[arg-type]
    ref = PullRequestRef.parse("owner/repo#1")

    build_context(mock_client, ref, config)

    _, kwargs = mock_client.get_changed_files.call_args
    assert kwargs["max_file_bytes"] == 2048


def test_accept_handles_binary_deleted_renamed() -> None:
    """build_context serializes ChangedFile objects with various statuses to dicts."""

    mock_client = MagicMock()
    mock_pr = _build_mock_pr()
    mock_client.get_pull_request.return_value = mock_pr
    mock_client.get_diff.return_value = ""
    mock_client.get_changed_files.return_value = [
        ChangedFile("image.png", "added", 0, 0, None, None),
        ChangedFile("old.py", "removed", 0, 10, "-code", None),
        ChangedFile("new.py", "renamed", 1, 1, "+new", "new", previous_filename="old.py"),
    ]
    mock_client.get_commit_messages.return_value = []
    mock_client.get_conventions_file.return_value = None

    config = LycheeConfig()
    ref = PullRequestRef.parse("owner/repo#1")

    ctx = build_context(mock_client, ref, config)

    assert len(ctx.changed_files) == 3
    # Binary
    assert ctx.changed_files[0]["content_at_head"] is None
    # Deleted
    assert ctx.changed_files[1]["status"] == "removed"
    # Renamed
    assert ctx.changed_files[2]["previous_filename"] == "old.py"
