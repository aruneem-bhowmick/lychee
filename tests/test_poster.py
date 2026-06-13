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
    from lychee.poster import PosterError, SummaryPoster  # noqa: F811

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
