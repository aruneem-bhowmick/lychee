"""PR review context assembly — fetches and bundles all data needed for a review."""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

import pydantic

from lychee.config import LycheeConfig, should_ignore_file
from lychee.github_client import GitHubClient, PullRequestRef

_logger = logging.getLogger(__name__)


class ReviewContext(pydantic.BaseModel):
    """All context assembled for a single PR review."""

    model_config = pydantic.ConfigDict(frozen=True)

    pr_number: int
    pr_title: str
    pr_body: str | None
    pr_author: str
    base_ref: str
    head_ref: str
    head_sha: str
    repo_full_name: str
    diff: str
    changed_files: list[dict[str, Any]]
    commit_messages: list[str]
    conventions: str | None = None


def build_context(
    client: GitHubClient,
    pr_ref: PullRequestRef,
    config: LycheeConfig,
    *,
    pr_labels: list[str] | None = None,
) -> ReviewContext:
    """Fetch and assemble all PR context needed for a review.

    Orchestrates calls to GitHubClient to gather PR metadata, diff,
    changed file contents, commit messages, and an optional conventions file.

    When ``pr_labels`` is provided and the config contains scope rules,
    files matching an ``ignore=True`` scope rule are filtered out of the
    returned context.
    """
    pr = client.get_pull_request(pr_ref)
    diff = client.get_diff(pr_ref)

    changed_files = client.get_changed_files(
        pr,
        max_files=config.review.max_files,
        max_file_bytes=config.review.max_file_bytes,
        ignore_globs=config.review.ignore_globs,
    )

    labels = pr_labels if pr_labels is not None else []
    scope_rules = config.review.scope_rules

    if scope_rules:
        before_count = len(changed_files)
        changed_files = [
            f for f in changed_files
            if not should_ignore_file(f.filename, scope_rules, labels)
        ]
        filtered_count = before_count - len(changed_files)
        if filtered_count:
            _logger.info(
                "Scope rules filtered %d file(s) from review context", filtered_count
            )

    commit_messages = client.get_commit_messages(pr)

    conventions = client.get_conventions_file(
        repo_full_name=pr_ref.full_name,
        path=config.conventions_file,
        ref=pr.head.sha,
    )

    serialized_files = [dataclasses.asdict(f) for f in changed_files]

    _logger.info(
        "Built review context for PR #%d: %d files, diff=%d chars, conventions=%s",
        pr.number,
        len(changed_files),
        len(diff),
        "loaded" if conventions else "none",
    )

    return ReviewContext(
        pr_number=pr.number,
        pr_title=pr.title,
        pr_body=pr.body,
        pr_author=pr.user.login,
        base_ref=pr.base.ref,
        head_ref=pr.head.ref,
        head_sha=pr.head.sha,
        repo_full_name=pr_ref.full_name,
        diff=diff,
        changed_files=serialized_files,
        commit_messages=commit_messages,
        conventions=conventions,
    )
