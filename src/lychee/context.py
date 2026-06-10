"""PR review context assembly — fetches and bundles all data needed for a review."""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

import pydantic

from lychee.config import LycheeConfig
from lychee.github_client import ChangedFile, GitHubClient, PullRequestRef

logger = logging.getLogger(__name__)


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
    pr_ref: str,
    config: LycheeConfig,
) -> ReviewContext:
    """Fetch and assemble all PR context needed for a review.

    Orchestrates calls to GitHubClient to gather PR metadata, diff,
    changed file contents, commit messages, and an optional conventions file.
    """
    ref = PullRequestRef.parse(pr_ref)

    pr = client.get_pull_request(ref)
    diff = client.get_diff(ref)

    changed_files = client.get_changed_files(
        pr,
        max_files=config.review.max_files,
        max_file_bytes=config.review.max_file_bytes,
        ignore_globs=config.review.ignore_globs,
    )

    commit_messages = client.get_commit_messages(pr)

    conventions = client.get_conventions_file(
        repo_full_name=ref.full_name,
        path=config.conventions_file,
        ref=pr.head.sha,
    )

    serialized_files = [dataclasses.asdict(f) for f in changed_files]

    logger.info(
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
        repo_full_name=ref.full_name,
        diff=diff,
        changed_files=serialized_files,
        commit_messages=commit_messages,
        conventions=conventions,
    )
