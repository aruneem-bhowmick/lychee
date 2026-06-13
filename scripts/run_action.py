"""GitHub Actions entrypoint — parses event and runs engine + poster."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from lychee.claude import ClaudeClient
from lychee.config import load_config
from lychee.github_client import GitHubClient, PullRequestRef
from lychee.poster import SummaryPoster
from lychee.render import render_comment
from lychee.review import run_review

_logger = logging.getLogger("lychee.action")

# Supported pull_request event actions
_SUPPORTED_ACTIONS: set[str] = {"opened", "synchronize", "reopened"}


def main() -> None:
    """Entry point for the GitHub Action.

    1. Read GITHUB_EVENT_PATH to get the event payload.
    2. Validate the event action is supported; exit 0 if not.
    3. Extract PR number, repo, and head SHA.
    4. Load config.
    5. Construct GitHubClient and ClaudeClient.
    6. Run the review engine.
    7. Render the comment.
    8. Post/upsert the comment with state.
    9. Exit 0 on success; exit 1 on failure (after logging).

    Reads from environment:
    - GITHUB_TOKEN: GitHub API token (Actions-provided)
    - ANTHROPIC_API_KEY: Claude API key (Actions secret)
    - GITHUB_EVENT_PATH: path to event JSON (Actions-provided)
    - GITHUB_REPOSITORY: owner/repo (Actions-provided)

    Raises SystemExit(0) on success or non-applicable event.
    Raises SystemExit(1) on failure.
    """
    logging.basicConfig(
        level=logging.INFO,
        format=(
            '{"time":"%(asctime)s","name":"%(name)s",'
            '"level":"%(levelname)s","message":"%(message)s"}'
        ),
    )

    try:
        github_token = os.environ.get("GITHUB_TOKEN")
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

        if not github_token:
            _logger.error("GITHUB_TOKEN environment variable is not set")
            sys.exit(1)
        if not anthropic_key:
            _logger.error("ANTHROPIC_API_KEY environment variable is not set")
            sys.exit(1)

        event_path = os.environ.get("GITHUB_EVENT_PATH", "")
        event = _parse_event(event_path)

        if not _is_applicable_event(event):
            action = event.get("action", "<missing>")
            _logger.info("Skipping non-applicable event action: %s", action)
            sys.exit(0)

        pr_number: int = event["pull_request"]["number"]
        repo: str = os.environ["GITHUB_REPOSITORY"]
        head_sha: str = event["pull_request"]["head"]["sha"]
        pr_ref = f"{repo}#{pr_number}"

        _logger.info("Starting review for %s (sha=%s)", pr_ref, head_sha)

        config = load_config()
        github_client = GitHubClient(token=github_token)
        claude_client = ClaudeClient(api_key=anthropic_key, model=config.model.default)

        result = run_review(pr_ref, config, github_client, claude_client)

        cost_line: str | None = None  # Cost footer computation deferred
        comment_body = render_comment(result, cost_line=cost_line)

        poster = SummaryPoster(github_client)
        pr_obj = github_client.get_pull_request(PullRequestRef.parse(pr_ref))
        state: dict[str, Any] = {"last_reviewed_sha": head_sha}
        poster.post(pr_obj, comment_body, state=state)

        _logger.info("Review posted for %s", pr_ref)
        sys.exit(0)

    except SystemExit:
        raise
    except Exception as exc:
        _logger.error("Review failed: %s", type(exc).__name__)
        sys.exit(1)


def _parse_event(event_path: str) -> dict[str, Any]:
    """Parse the GitHub event JSON file.

    Raises SystemExit(1) if the file is missing or malformed.
    """
    try:
        text = Path(event_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        _logger.error("Event file not found: %s", event_path)
        sys.exit(1)
    except OSError as exc:
        _logger.error("Cannot read event file %s: %s", event_path, exc)
        sys.exit(1)

    try:
        data: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as exc:
        _logger.error("Malformed event JSON in %s: %s", event_path, exc)
        sys.exit(1)

    return data


def _is_applicable_event(event: dict[str, Any]) -> bool:
    """Return True if the event action is in _SUPPORTED_ACTIONS."""
    return event.get("action") in _SUPPORTED_ACTIONS


if __name__ == "__main__":
    main()
