"""Unit, integration, acceptance, regression, and API tests for lychee.poster.

Covers SummaryPoster comment upsert logic, state marker serialisation,
and GitHub API interaction.  All GitHub calls are mocked; no live calls.

Framework: pytest.  Coverage target: >= 90% on src/lychee/poster.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lychee.models import Category, Finding, ReviewResult, Ripeness, Severity
from lychee.poster import (
    STATE_MARKER_PREFIX,
    STATE_MARKER_SUFFIX,
    InlinePostResult,
    InlineReviewPoster,
    PosterError,
    SummaryPoster,
)
from lychee.render import REVIEW_MARKER

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_comment(body: str, comment_id: int = 100) -> MagicMock:
    """Create a mock IssueComment with a given body and id."""
    comment = MagicMock()
    comment.body = body
    comment.id = comment_id
    return comment


def _make_mock_pr(comments: list[MagicMock] | None = None) -> MagicMock:
    """Create a mock PullRequest with optional pre-configured issue comments."""
    pr = MagicMock()
    pr.get_issue_comments.return_value = comments or []
    new_comment = MagicMock()
    new_comment.id = 999
    pr.create_issue_comment.return_value = new_comment
    return pr


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_poster_imports() -> None:
    """SummaryPoster and PosterError import cleanly from lychee.poster."""
    from lychee.poster import PosterError, SummaryPoster

    assert callable(SummaryPoster)
    assert issubclass(PosterError, Exception)


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_poster_instantiates() -> None:
    """SummaryPoster constructs without error given a mock client."""
    mock_client = MagicMock()
    poster = SummaryPoster(mock_client)
    assert poster is not None


# ---------------------------------------------------------------------------
# Unit tests — pure static methods
# ---------------------------------------------------------------------------


def test_append_state_marker() -> None:
    """_append_state_marker appends the expected marker string to a body."""
    body = "Hello world"
    state = {"last_reviewed_sha": "abc123"}
    result = SummaryPoster._append_state_marker(body, state)
    assert result.endswith('<!-- lychee:state {"last_reviewed_sha":"abc123"} -->')
    assert result.startswith("Hello world")


def test_append_state_marker_empty_dict() -> None:
    """_append_state_marker with an empty dict appends <!-- lychee:state {} -->."""
    body = "Some body"
    result = SummaryPoster._append_state_marker(body, {})
    assert "<!-- lychee:state {} -->" in result


def test_extract_state_present() -> None:
    """extract_state returns the state dict when the marker is present."""
    body = 'Review content\n\n<!-- lychee:state {"last_reviewed_sha":"abc123"} -->'
    state = SummaryPoster.extract_state(body)
    assert state == {"last_reviewed_sha": "abc123"}


def test_extract_state_absent() -> None:
    """extract_state returns None when no state marker is present."""
    body = "Just a plain comment body."
    assert SummaryPoster.extract_state(body) is None


def test_extract_state_malformed_json() -> None:
    """extract_state returns None when the marker contains invalid JSON."""
    body = "Review\n\n<!-- lychee:state {bad json} -->"
    assert SummaryPoster.extract_state(body) is None


def test_extract_state_round_trip() -> None:
    """extract_state(_append_state_marker(body, state)) equals state."""
    body = "Original body"
    state = {"last_reviewed_sha": "deadbeef", "run_count": 3}
    combined = SummaryPoster._append_state_marker(body, state)
    extracted = SummaryPoster.extract_state(combined)
    assert extracted == state


def test_state_marker_at_end() -> None:
    """State marker appears at the very end of the body, after existing content."""
    body = "Header\n\n*Footer*"
    state = {"sha": "abc"}
    result = SummaryPoster._append_state_marker(body, state)
    # The state marker should be the last line
    assert result.endswith(STATE_MARKER_SUFFIX)
    # And the original footer should appear before it
    assert result.index("*Footer*") < result.index(STATE_MARKER_PREFIX)


# ---------------------------------------------------------------------------
# Integration tests (mocked GitHub API)
# ---------------------------------------------------------------------------


def test_post_creates_new_comment() -> None:
    """When no existing marker comment exists, create_issue_comment is called."""
    pr = _make_mock_pr(comments=[])
    poster = SummaryPoster(MagicMock())

    poster.post(pr, "Review body")

    pr.create_issue_comment.assert_called_once()
    # edit should not have been called on any comment
    for comment in pr.get_issue_comments():
        comment.edit.assert_not_called()


def test_post_updates_existing_comment() -> None:
    """When a marker comment exists, edit is called instead of create."""
    existing = _make_mock_comment(f"{REVIEW_MARKER}\nOld review", comment_id=42)
    pr = _make_mock_pr(comments=[existing])
    poster = SummaryPoster(MagicMock())

    poster.post(pr, "New review body")

    existing.edit.assert_called_once()
    pr.create_issue_comment.assert_not_called()


def test_post_returns_comment_id() -> None:
    """post() returns the comment ID (new or existing)."""
    pr = _make_mock_pr(comments=[])
    poster = SummaryPoster(MagicMock())

    comment_id = poster.post(pr, "Body")
    assert comment_id == 999  # from _make_mock_pr default


def test_post_returns_existing_comment_id() -> None:
    """post() returns the existing comment's ID when editing."""
    existing = _make_mock_comment(f"{REVIEW_MARKER}\nOld", comment_id=42)
    pr = _make_mock_pr(comments=[existing])
    poster = SummaryPoster(MagicMock())

    comment_id = poster.post(pr, "Updated body")
    assert comment_id == 42


def test_post_with_state() -> None:
    """When state is provided, the posted body contains the state marker."""
    pr = _make_mock_pr(comments=[])
    poster = SummaryPoster(MagicMock())

    poster.post(pr, "Body", state={"last_reviewed_sha": "abc"})

    call_args = pr.create_issue_comment.call_args
    posted_body: str = call_args.kwargs["body"]
    assert STATE_MARKER_PREFIX in posted_body
    assert '"last_reviewed_sha":"abc"' in posted_body


def test_post_without_state() -> None:
    """When state is None, the posted body does not contain the state marker."""
    pr = _make_mock_pr(comments=[])
    poster = SummaryPoster(MagicMock())

    poster.post(pr, "Body", state=None)

    call_args = pr.create_issue_comment.call_args
    posted_body: str = call_args.kwargs["body"]
    assert "<!-- lychee:state" not in posted_body


def test_find_existing_comment_found() -> None:
    """_find_existing_comment returns the comment containing REVIEW_MARKER."""
    marker_comment = _make_mock_comment(f"{REVIEW_MARKER}\nReview content", comment_id=7)
    other_comment = _make_mock_comment("Just a regular comment", comment_id=8)
    pr = _make_mock_pr(comments=[other_comment, marker_comment])
    poster = SummaryPoster(MagicMock())

    result = poster._find_existing_comment(pr)
    assert result is marker_comment


def test_find_existing_comment_not_found() -> None:
    """_find_existing_comment returns None when no comment has the marker."""
    other = _make_mock_comment("No marker here", comment_id=1)
    pr = _make_mock_pr(comments=[other])
    poster = SummaryPoster(MagicMock())

    result = poster._find_existing_comment(pr)
    assert result is None


def test_find_existing_comment_deleted_between_runs() -> None:
    """When comments list is empty (deleted), _find returns None and post creates new."""
    pr = _make_mock_pr(comments=[])
    poster = SummaryPoster(MagicMock())

    result = poster._find_existing_comment(pr)
    assert result is None

    # Subsequent post should create a new comment
    comment_id = poster.post(pr, "New review")
    assert comment_id == 999
    pr.create_issue_comment.assert_called_once()


def test_post_github_error_raises() -> None:
    """GithubException during create_issue_comment raises PosterError."""
    from github import GithubException

    pr = _make_mock_pr(comments=[])
    pr.create_issue_comment.side_effect = GithubException(500, "Server Error", None)
    poster = SummaryPoster(MagicMock())

    with pytest.raises(PosterError, match="GitHub API error"):
        poster.post(pr, "Body")


def test_post_edit_github_error_raises() -> None:
    """GithubException during comment.edit raises PosterError."""
    from github import GithubException

    existing = _make_mock_comment(f"{REVIEW_MARKER}\nOld", comment_id=10)
    existing.edit.side_effect = GithubException(500, "Server Error", None)
    pr = _make_mock_pr(comments=[existing])
    poster = SummaryPoster(MagicMock())

    with pytest.raises(PosterError, match="GitHub API error"):
        poster.post(pr, "Updated")


def test_multiple_marker_comments_warns(caplog: pytest.LogCaptureFixture) -> None:
    """When multiple comments have the marker, a warning is logged and the first is returned."""
    import logging

    first = _make_mock_comment(f"{REVIEW_MARKER}\nFirst", comment_id=1)
    second = _make_mock_comment(f"{REVIEW_MARKER}\nSecond", comment_id=2)
    pr = _make_mock_pr(comments=[first, second])
    poster = SummaryPoster(MagicMock())

    with caplog.at_level(logging.WARNING, logger="lychee.poster"):
        result = poster._find_existing_comment(pr)

    assert result is first
    assert "extra comment(s) with review marker" in caplog.text


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_first_run_creates() -> None:
    """Acceptance: first call on a PR with no marker comments creates one."""
    pr = _make_mock_pr(comments=[])
    poster = SummaryPoster(MagicMock())

    comment_id = poster.post(pr, f"{REVIEW_MARKER}\nReview body")

    assert isinstance(comment_id, int)
    pr.create_issue_comment.assert_called_once()


def test_accept_subsequent_run_edits() -> None:
    """Acceptance: second call with existing marker comment edits it."""
    existing = _make_mock_comment(f"{REVIEW_MARKER}\nOld review", comment_id=50)
    pr = _make_mock_pr(comments=[existing])
    poster = SummaryPoster(MagicMock())

    comment_id = poster.post(pr, f"{REVIEW_MARKER}\nNew review")

    assert comment_id == 50
    existing.edit.assert_called_once()
    pr.create_issue_comment.assert_not_called()


def test_accept_no_duplicate() -> None:
    """Acceptance: after two post() calls, only one marker comment exists."""
    # First call: no existing comments → creates one
    pr = _make_mock_pr(comments=[])
    poster = SummaryPoster(MagicMock())

    poster.post(pr, f"{REVIEW_MARKER}\nFirst review")
    pr.create_issue_comment.assert_called_once()

    # Simulate the created comment now existing
    created_comment = _make_mock_comment(f"{REVIEW_MARKER}\nFirst review", comment_id=999)
    pr.get_issue_comments.return_value = [created_comment]

    # Second call: finds existing → edits, no new comment
    poster.post(pr, f"{REVIEW_MARKER}\nSecond review")
    # create_issue_comment should still only have been called once (from the first post)
    assert pr.create_issue_comment.call_count == 1
    created_comment.edit.assert_called_once()


def test_accept_state_marker_round_trips() -> None:
    """Acceptance: state written by post() can be read back by extract_state()."""
    pr = _make_mock_pr(comments=[])
    poster = SummaryPoster(MagicMock())
    state = {"last_reviewed_sha": "abc123"}

    poster.post(pr, "Review body", state=state)

    # Get the body that was posted
    call_args = pr.create_issue_comment.call_args
    posted_body: str = call_args.kwargs["body"]
    extracted = SummaryPoster.extract_state(posted_body)
    assert extracted == state


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def test_state_marker_format_snapshot() -> None:
    """State marker for a known dict matches an exact pinned string."""
    state = {"last_reviewed_sha": "abc123"}
    body = SummaryPoster._append_state_marker("body", state)
    expected_marker = '<!-- lychee:state {"last_reviewed_sha":"abc123"} -->'
    assert expected_marker in body


def test_upsert_idempotency() -> None:
    """Posting the same body twice to a PR with existing comment results in one edit call."""
    body = f"{REVIEW_MARKER}\nReview content"
    existing = _make_mock_comment(body, comment_id=77)
    pr = _make_mock_pr(comments=[existing])
    poster = SummaryPoster(MagicMock())

    poster.post(pr, body)
    poster.post(pr, body)

    assert existing.edit.call_count == 2
    # Both edit calls should have the same body
    first_body = existing.edit.call_args_list[0].kwargs["body"]
    second_body = existing.edit.call_args_list[1].kwargs["body"]
    assert first_body == second_body


def test_extract_state_missing_suffix() -> None:
    """extract_state returns None when the prefix exists but suffix is missing."""
    body = '<!-- lychee:state {"sha":"abc"}'
    assert SummaryPoster.extract_state(body) is None


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


def test_api_create_comment_called_with_body() -> None:
    """pr.create_issue_comment is called with the exact final body string."""
    pr = _make_mock_pr(comments=[])
    poster = SummaryPoster(MagicMock())
    body = "Exact body content"

    poster.post(pr, body)

    pr.create_issue_comment.assert_called_once_with(body=body)


def test_api_edit_comment_called_with_body() -> None:
    """comment.edit is called with the exact final body string."""
    existing = _make_mock_comment(f"{REVIEW_MARKER}\nOld", comment_id=10)
    pr = _make_mock_pr(comments=[existing])
    poster = SummaryPoster(MagicMock())
    body = "Updated body content"

    poster.post(pr, body)

    existing.edit.assert_called_once_with(body=body)


def test_api_get_issue_comments_called() -> None:
    """pr.get_issue_comments() is called to scan for the existing marker."""
    pr = _make_mock_pr(comments=[])
    poster = SummaryPoster(MagicMock())

    poster.post(pr, "Body")

    pr.get_issue_comments.assert_called()


def test_api_edit_with_state_body() -> None:
    """When editing with state, comment.edit receives the body with state marker appended."""
    existing = _make_mock_comment(f"{REVIEW_MARKER}\nOld", comment_id=10)
    pr = _make_mock_pr(comments=[existing])
    poster = SummaryPoster(MagicMock())
    state = {"sha": "deadbeef"}

    poster.post(pr, "Body", state=state)

    call_args = existing.edit.call_args
    edited_body: str = call_args.kwargs["body"]
    assert STATE_MARKER_PREFIX in edited_body
    assert '"sha":"deadbeef"' in edited_body


# ===========================================================================
# InlineReviewPoster tests
# ===========================================================================

# Minimal diff where src/app.py line 2 is an added line.
_INLINE_DIFF = """\
diff --git a/src/app.py b/src/app.py
index aaa..bbb 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
 import os
+import sys

 def main():
"""


def _make_mock_pr_with_review(
    comments: list[MagicMock] | None = None,
    review_id: int = 200,
) -> MagicMock:
    """Create a mock PullRequest with create_review support."""
    pr = _make_mock_pr(comments)
    mock_review = MagicMock()
    mock_review.id = review_id
    pr.create_review.return_value = mock_review
    return pr


def _make_review_result(findings: list[Finding] | None = None) -> ReviewResult:
    """Create a ReviewResult with optional findings."""
    return ReviewResult(
        ripeness=Ripeness.ripe,
        summary="Test summary.",
        walkthrough="Test walkthrough.",
        findings=findings or [],
        model="test-model",
        usage={"input_tokens": 100, "output_tokens": 50},
    )


def _make_inline_finding(
    file: str = "src/app.py",
    line: int | None = 2,
    severity: Severity = Severity.minor,
    category: Category = Category.style,
    message: str = "Test finding.",
    suggestion: str | None = None,
) -> Finding:
    """Create a Finding suitable for inline tests."""
    return Finding(
        file=file,
        line=line,
        severity=severity,
        category=category,
        message=message,
        suggestion=suggestion,
    )


# ---------------------------------------------------------------------------
# Smoke tests — InlineReviewPoster
# ---------------------------------------------------------------------------


def test_inline_poster_imports() -> None:
    """InlineReviewPoster and InlinePostResult import cleanly."""
    from lychee.poster import InlinePostResult, InlineReviewPoster

    assert callable(InlineReviewPoster)
    assert InlinePostResult is not None


# ---------------------------------------------------------------------------
# Sanity tests — InlineReviewPoster
# ---------------------------------------------------------------------------


def test_inline_poster_instantiates() -> None:
    """InlineReviewPoster constructs without error given a mock client."""
    poster = InlineReviewPoster(MagicMock())
    assert poster is not None


def test_inline_post_result_is_frozen() -> None:
    """InlinePostResult is a frozen dataclass."""
    result = InlinePostResult(
        review_id=1, inline_count=0, fallback_count=0, fallback_findings=[]
    )
    with pytest.raises(AttributeError):
        result.review_id = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Unit tests — _partition_findings
# ---------------------------------------------------------------------------


def test_partition_all_inline() -> None:
    """All findings map to inline positions."""
    from lychee.diff_mapping import build_position_map

    pmap = build_position_map(_INLINE_DIFF)
    findings = [_make_inline_finding(file="src/app.py", line=2)]
    inline, fallback = InlineReviewPoster._partition_findings(findings, pmap, "info")
    assert len(inline) == 1
    assert len(fallback) == 0


def test_partition_all_fallback() -> None:
    """Findings with no diff position go to fallback."""
    from lychee.diff_mapping import build_position_map

    pmap = build_position_map(_INLINE_DIFF)
    findings = [_make_inline_finding(file="src/app.py", line=None)]
    inline, fallback = InlineReviewPoster._partition_findings(findings, pmap, "info")
    assert len(inline) == 0
    assert len(fallback) == 1


def test_partition_mixed() -> None:
    """Mix of inline and fallback findings."""
    from lychee.diff_mapping import build_position_map

    pmap = build_position_map(_INLINE_DIFF)
    findings = [
        _make_inline_finding(file="src/app.py", line=2),
        _make_inline_finding(file="src/app.py", line=None),
        _make_inline_finding(file="src/other.py", line=5),
    ]
    inline, fallback = InlineReviewPoster._partition_findings(findings, pmap, "info")
    assert len(inline) == 1
    assert len(fallback) == 2


def test_partition_severity_filtering() -> None:
    """Findings below threshold are excluded entirely."""
    from lychee.diff_mapping import build_position_map

    pmap = build_position_map(_INLINE_DIFF)
    findings = [
        _make_inline_finding(severity=Severity.info, line=2),
        _make_inline_finding(severity=Severity.major, line=2),
    ]
    inline, fallback = InlineReviewPoster._partition_findings(findings, pmap, "major")
    assert len(inline) == 1
    assert inline[0][0].severity == Severity.major
    assert len(fallback) == 0


# ---------------------------------------------------------------------------
# Unit tests — _build_review_comments
# ---------------------------------------------------------------------------


def test_build_review_comments_format() -> None:
    """Built comments have path, position, and body keys."""
    from lychee.diff_mapping import DiffPosition

    finding = _make_inline_finding()
    pos = DiffPosition(path="src/app.py", position=3, line=2)
    comments = InlineReviewPoster._build_review_comments([(finding, pos)])
    assert len(comments) == 1
    comment = comments[0]
    assert set(comment.keys()) == {"path", "position", "body"}
    assert comment["path"] == "src/app.py"
    assert comment["position"] == 3


def test_build_review_comments_body_content() -> None:
    """Comment body matches render_inline_comment output."""
    from lychee.diff_mapping import DiffPosition
    from lychee.inline_render import render_inline_comment

    finding = _make_inline_finding(message="Custom msg.")
    pos = DiffPosition(path="src/app.py", position=3, line=2)
    comments = InlineReviewPoster._build_review_comments([(finding, pos)])
    assert comments[0]["body"] == render_inline_comment(finding)


# ---------------------------------------------------------------------------
# Integration tests (mocked GitHub) — InlineReviewPoster
# ---------------------------------------------------------------------------


def test_inline_single_finding_posts_review() -> None:
    """Single mappable finding triggers create_review."""
    pr = _make_mock_pr_with_review()
    result = _make_review_result([_make_inline_finding(line=2)])
    poster = InlineReviewPoster(MagicMock())

    post_result = poster.post(pr, result, _INLINE_DIFF)

    assert post_result.review_id == 200
    assert post_result.inline_count == 1
    assert post_result.fallback_count == 0
    pr.create_review.assert_called_once()


def test_inline_multiple_findings_one_review() -> None:
    """Multiple mappable findings result in one create_review call."""
    pr = _make_mock_pr_with_review()
    result = _make_review_result([
        _make_inline_finding(line=1),
        _make_inline_finding(line=2),
    ])
    poster = InlineReviewPoster(MagicMock())

    post_result = poster.post(pr, result, _INLINE_DIFF)

    assert post_result.inline_count == 2
    pr.create_review.assert_called_once()


def test_inline_no_mappable_skips_review() -> None:
    """No mappable findings skips create_review entirely."""
    pr = _make_mock_pr_with_review()
    result = _make_review_result([_make_inline_finding(line=None)])
    poster = InlineReviewPoster(MagicMock())

    post_result = poster.post(pr, result, _INLINE_DIFF)

    assert post_result.review_id is None
    assert post_result.inline_count == 0
    assert post_result.fallback_count == 1
    pr.create_review.assert_not_called()


def test_inline_github_exception_raises_poster_error() -> None:
    """GithubException during create_review raises PosterError."""
    from github import GithubException

    pr = _make_mock_pr_with_review()
    pr.create_review.side_effect = GithubException(500, "Server Error", None)
    result = _make_review_result([_make_inline_finding(line=2)])
    poster = InlineReviewPoster(MagicMock())

    with pytest.raises(PosterError, match="GitHub API error"):
        poster.post(pr, result, _INLINE_DIFF)


def test_inline_fallback_findings_returned() -> None:
    """Fallback findings are returned in the result."""
    pr = _make_mock_pr_with_review()
    file_level = _make_inline_finding(line=None, message="File-level note.")
    result = _make_review_result([
        _make_inline_finding(line=2),
        file_level,
    ])
    poster = InlineReviewPoster(MagicMock())

    post_result = poster.post(pr, result, _INLINE_DIFF)

    assert post_result.fallback_count == 1
    assert len(post_result.fallback_findings) == 1
    assert post_result.fallback_findings[0].message == "File-level note."


# ---------------------------------------------------------------------------
# System tests — InlineReviewPoster with diff_simple fixture
# ---------------------------------------------------------------------------


def test_system_full_flow_with_diff_simple(diff_simple: str) -> None:
    """Full flow: realistic findings against diff_simple fixture."""
    pr = _make_mock_pr_with_review()
    # Line 1 of src/utils.py is an added line in diff_simple
    findings = [
        _make_inline_finding(file="src/utils.py", line=1, message="Docstring present."),
        _make_inline_finding(file="src/utils.py", line=None, message="File note."),
        _make_inline_finding(file="nonexistent.py", line=5, message="Not in diff."),
    ]
    result = _make_review_result(findings)
    poster = InlineReviewPoster(MagicMock())

    post_result = poster.post(pr, result, diff_simple)

    assert post_result.inline_count == 1
    assert post_result.fallback_count == 2
    assert post_result.review_id == 200


# ---------------------------------------------------------------------------
# Acceptance tests — InlineReviewPoster
# ---------------------------------------------------------------------------


def test_accept_review_event_is_comment() -> None:
    """Review event is 'COMMENT' (not APPROVE/REQUEST_CHANGES)."""
    pr = _make_mock_pr_with_review()
    result = _make_review_result([_make_inline_finding(line=2)])
    poster = InlineReviewPoster(MagicMock())

    poster.post(pr, result, _INLINE_DIFF)

    call_kwargs = pr.create_review.call_args.kwargs
    assert call_kwargs["event"] == "COMMENT"


def test_accept_multiple_pits_one_review_call() -> None:
    """Multiple findings produce exactly one create_review call."""
    pr = _make_mock_pr_with_review()
    result = _make_review_result([
        _make_inline_finding(line=1, severity=Severity.critical),
        _make_inline_finding(line=2, severity=Severity.minor),
    ])
    poster = InlineReviewPoster(MagicMock())

    poster.post(pr, result, _INLINE_DIFF)

    assert pr.create_review.call_count == 1


def test_accept_severities_in_comment_bodies() -> None:
    """Comment bodies contain severity labels and categories."""
    pr = _make_mock_pr_with_review()
    result = _make_review_result([
        _make_inline_finding(
            line=2, severity=Severity.critical, category=Category.security
        ),
    ])
    poster = InlineReviewPoster(MagicMock())

    poster.post(pr, result, _INLINE_DIFF)

    comments = pr.create_review.call_args.kwargs["comments"]
    body = comments[0]["body"]
    assert "Critical" in body
    assert "security" in body


# ---------------------------------------------------------------------------
# API tests — InlineReviewPoster
# ---------------------------------------------------------------------------


def test_api_create_review_params() -> None:
    """create_review is called with event and comments kwargs only (no body)."""
    pr = _make_mock_pr_with_review()
    result = _make_review_result([_make_inline_finding(line=2)])
    poster = InlineReviewPoster(MagicMock())

    poster.post(pr, result, _INLINE_DIFF)

    call_kwargs = pr.create_review.call_args.kwargs
    assert "event" in call_kwargs
    assert "comments" in call_kwargs
    assert "body" not in call_kwargs


# ---------------------------------------------------------------------------
# Regression tests — InlineReviewPoster
# ---------------------------------------------------------------------------


def test_regression_review_comments_snapshot() -> None:
    """Review comments for a fixed input match an expected structure."""
    from lychee.diff_mapping import DiffPosition
    from lychee.inline_render import render_inline_comment

    finding = _make_inline_finding(
        file="src/app.py",
        line=2,
        severity=Severity.minor,
        category=Category.style,
        message="Import order.",
    )
    pos = DiffPosition(path="src/app.py", position=3, line=2)
    comments = InlineReviewPoster._build_review_comments([(finding, pos)])

    assert comments == [
        {
            "path": "src/app.py",
            "position": 3,
            "body": render_inline_comment(finding),
        }
    ]
