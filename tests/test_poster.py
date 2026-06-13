"""Unit, integration, acceptance, regression, and API tests for lychee.poster.

Covers SummaryPoster comment upsert logic, state marker serialisation,
and GitHub API interaction.  All GitHub calls are mocked; no live calls.

Framework: pytest.  Coverage target: >= 90% on src/lychee/poster.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lychee.poster import (
    STATE_MARKER_PREFIX,
    STATE_MARKER_SUFFIX,
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
