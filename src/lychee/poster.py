"""PR comment poster — upserts the lychee review comment on a pull request."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from github import GithubException

from lychee.diff_mapping import DiffPosition, build_position_map, map_finding_to_position
from lychee.inline_render import render_inline_comment
from lychee.models import Finding
from lychee.render import REVIEW_MARKER, severity_at_or_above

_logger = logging.getLogger(__name__)

STATE_MARKER_PREFIX = "<!-- lychee:state "
STATE_MARKER_SUFFIX = " -->"


class PosterError(Exception):
    """Raised when comment upsert fails."""


class SummaryPoster:
    """Upserts the lychee marker comment on a PR."""

    def __init__(self, github_client: Any) -> None:
        """Initialise the poster with a GitHubClient instance.

        The client is used to access the PyGithub objects for comment operations.
        """
        self._github_client = github_client

    def post(
        self,
        pr: Any,  # github.PullRequest.PullRequest
        comment_body: str,
        state: dict[str, Any] | None = None,
    ) -> int:
        """Create or update the lychee review comment on a PR.

        Appends the state marker if *state* is provided, then scans existing
        comments for ``REVIEW_MARKER``.  If found the existing comment is
        edited in place; otherwise a new comment is created.

        Returns the comment ID.

        Raises ``PosterError`` on GitHub API failures.
        """
        final_body = comment_body
        if state is not None:
            final_body = self._append_state_marker(final_body, state)
            _logger.debug("State dict: %s", state)

        try:
            existing = self._find_existing_comment(pr)

            if existing is not None:
                existing.edit(body=final_body)
                _logger.info("Updated existing comment #%d", existing.id)
                return existing.id  # type: ignore[no-any-return]

            new_comment = pr.create_issue_comment(body=final_body)
            _logger.info("Created new comment #%d", new_comment.id)
            return new_comment.id  # type: ignore[no-any-return]
        except GithubException as exc:
            raise PosterError(f"GitHub API error during comment upsert: {exc}") from exc

    def _find_existing_comment(
        self,
        pr: Any,  # github.PullRequest.PullRequest
    ) -> Any | None:
        """Find the existing lychee review comment on a PR, or None.

        Scans issue comments for one containing ``REVIEW_MARKER``.
        Returns the first matching ``IssueComment`` object, or ``None``.
        """
        match: Any | None = None
        extra_count = 0

        for comment in pr.get_issue_comments():
            if REVIEW_MARKER in comment.body:
                if match is None:
                    match = comment
                else:
                    extra_count += 1

        if extra_count > 0 and match is not None:
            _logger.warning(
                "Found %d extra comment(s) with review marker; using first (id=%d)",
                extra_count,
                match.id,
            )

        return match

    @staticmethod
    def _append_state_marker(body: str, state: dict[str, Any]) -> str:
        """Append the machine-readable state marker to the comment body.

        Format: ``<!-- lychee:state {"key":"value"} -->``
        JSON is compact (no extra whitespace).
        """
        json_state = json.dumps(state, separators=(",", ":"))
        return f"{body}\n\n{STATE_MARKER_PREFIX}{json_state}{STATE_MARKER_SUFFIX}"

    @staticmethod
    def extract_state(comment_body: str) -> dict[str, Any] | None:
        """Extract the state dict from a comment body, or None if absent.

        Parses the ``<!-- lychee:state {...} -->`` marker from the end of the
        body.  Returns ``None`` if no state marker is found or if the JSON is
        malformed.
        """
        idx = comment_body.rfind(STATE_MARKER_PREFIX)
        if idx == -1:
            return None

        start = idx + len(STATE_MARKER_PREFIX)
        end = comment_body.find(STATE_MARKER_SUFFIX, start)
        if end == -1:
            return None

        json_str = comment_body[start:end]
        try:
            parsed: dict[str, Any] = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        return parsed


@dataclass(frozen=True)
class InlinePostResult:
    """Result of an inline review comment posting operation.

    Attributes:
        review_id: The GitHub review ID, or ``None`` if no review was created.
        inline_count: Number of findings posted as inline comments.
        fallback_count: Number of findings that could not be posted inline.
        fallback_findings: The list of unmappable findings (for summary comment).
    """

    review_id: int | None
    inline_count: int
    fallback_count: int
    fallback_findings: list[Finding] = field(default_factory=list)


class InlineReviewPoster:
    """Posts review findings as inline comments on specific diff lines."""

    def __init__(self, github_client: Any) -> None:
        """Initialise with a GitHubClient instance."""
        self._github_client = github_client

    def post(
        self,
        pr: Any,  # github.PullRequest.PullRequest
        result: Any,  # ReviewResult
        diff: str,
        severity_threshold: str = "info",
        previous_state: dict[str, Any] | None = None,
    ) -> InlinePostResult:
        """Post findings as inline review comments on the PR.

        Builds a position map from the diff, partitions findings into
        inline-mappable and fallback, renders comments, and submits a
        single review via ``pr.create_review()``.

        Returns an ``InlinePostResult`` with counts and fallback findings.

        Raises ``PosterError`` on GitHub API failures.
        """
        position_map = build_position_map(diff)
        inline_pairs, fallback = self._partition_findings(
            result.findings, position_map, severity_threshold
        )

        if not inline_pairs:
            return InlinePostResult(
                review_id=None,
                inline_count=0,
                fallback_count=len(fallback),
                fallback_findings=fallback,
            )

        comments = self._build_review_comments(inline_pairs)

        try:
            review = pr.create_review(event="COMMENT", comments=comments)
            review_id: int = review.id
        except GithubException as exc:
            raise PosterError(f"GitHub API error during inline review: {exc}") from exc

        _logger.info(
            "Posted inline review #%d with %d comments (%d fallback)",
            review_id,
            len(inline_pairs),
            len(fallback),
        )

        return InlinePostResult(
            review_id=review_id,
            inline_count=len(inline_pairs),
            fallback_count=len(fallback),
            fallback_findings=fallback,
        )

    @staticmethod
    def _partition_findings(
        findings: list[Finding],
        position_map: dict[str, dict[int, DiffPosition]],
        severity_threshold: str,
    ) -> tuple[list[tuple[Finding, DiffPosition]], list[Finding]]:
        """Split findings into inline-mappable pairs and fallback list.

        Findings below the severity threshold are excluded entirely.
        """
        inline: list[tuple[Finding, DiffPosition]] = []
        fallback: list[Finding] = []

        for finding in findings:
            if not severity_at_or_above(finding.severity.value, severity_threshold):
                continue

            pos = map_finding_to_position(finding.file, finding.line, position_map)
            if pos is not None:
                inline.append((finding, pos))
            else:
                fallback.append(finding)

        return inline, fallback

    @staticmethod
    def _build_review_comments(
        inline_pairs: list[tuple[Finding, DiffPosition]],
    ) -> list[dict[str, Any]]:
        """Build the list of review comment dicts for ``pr.create_review()``.

        Each dict has ``path``, ``position``, and ``body`` keys.
        """
        return [
            {
                "path": pos.path,
                "position": pos.position,
                "body": render_inline_comment(finding),
            }
            for finding, pos in inline_pairs
        ]
