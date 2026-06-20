"""GitHub Actions entrypoint — parses event and runs engine + poster."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from lychee.authorization import format_refusal, is_authorized
from lychee.claude import ClaudeClient
from lychee.command_render import COMMAND_RENDERERS
from lychee.commands import HELP_TEXT, Command, ParsedCommand, UnknownCommand, parse_command
from lychee.config import LycheeConfig, load_config
from lychee.cost import BudgetExceededError, compute_cost, format_cost_line
from lychee.dedup import build_inline_state
from lychee.github_client import GitHubClient, PullRequestRef
from lychee.observability import (
    build_run_record,
    compute_finding_counts,
    emit_run_record,
    get_review_strategy,
    get_triage_verdict,
    new_correlation_id,
    setup_structured_logging,
)
from lychee.poster import InlineReviewPoster, PosterError, SummaryPoster
from lychee.render import render_comment
from lychee.review import run_review

__all__ = [
    "InlineReviewPoster",
    "PosterError",
    "build_inline_state",
    "main",
]

_logger = logging.getLogger("lychee.action")

# Supported pull_request event actions
_SUPPORTED_ACTIONS: set[str] = {"opened", "synchronize", "reopened"}

# Supported issue_comment event actions for command dispatch
_COMMAND_ACTIONS: set[str] = {"created"}


def main() -> None:
    """Entry point for the GitHub Action.

    Handles two event types:
    - ``pull_request``: runs the automatic review flow.
    - ``issue_comment``: routes @lychee commands through authorization
      to the review engine and posts command-specific responses.

    Reads from environment:
    - GITHUB_TOKEN: GitHub API token (Actions-provided)
    - ANTHROPIC_API_KEY: Claude API key (Actions secret)
    - GITHUB_EVENT_PATH: path to event JSON (Actions-provided)
    - GITHUB_REPOSITORY: owner/repo (Actions-provided)

    Raises SystemExit(0) on success or non-applicable event.
    Raises SystemExit(1) on failure.
    """
    new_correlation_id()
    setup_structured_logging()

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

        config = load_config()

        # Route to command handler if this is an issue_comment event on a PR.
        if _is_command_event(event):
            if not config.features.commands:
                _logger.info("Command events disabled (features.commands=False); skipping")
                sys.exit(0)

            github_client = GitHubClient(token=github_token)
            claude_client = ClaudeClient(api_key=anthropic_key, model=config.model.default)
            _handle_command_event(event, config, github_client, claude_client)
            return  # _handle_command_event calls sys.exit internally

        # Existing pull_request review flow.
        if not _is_applicable_event(event):
            action = event.get("action", "<missing>")
            _logger.info("Skipping non-applicable event action: %s", action)
            sys.exit(0)

        pr_number: int = event["pull_request"]["number"]
        repo: str = os.environ["GITHUB_REPOSITORY"]
        head_sha: str = event["pull_request"]["head"]["sha"]
        pr_ref = f"{repo}#{pr_number}"

        _logger.info("Starting review for %s (sha=%s)", pr_ref, head_sha)

        github_client = GitHubClient(token=github_token)
        claude_client = ClaudeClient(api_key=anthropic_key, model=config.model.default)

        start = time.monotonic()
        result = run_review(pr_ref, config, github_client, claude_client)
        duration = time.monotonic() - start

        cost_usd = compute_cost(result.usage, result.model)
        cost_line: str | None = None
        if config.features.cost_footer:
            cost_line = format_cost_line(cost_usd, result.usage)
        _logger.info("Review cost: $%.4f", cost_usd)

        run_record = build_run_record(
            repo=repo,
            pr_number=pr_number,
            head_sha=head_sha,
            model=result.model,
            usage=result.usage,
            cost_usd=cost_usd,
            ripeness=result.ripeness.value,
            finding_counts=compute_finding_counts(result.findings),
            duration_seconds=duration,
            review_strategy=get_review_strategy(),
            triage_verdict=get_triage_verdict(),
        )
        emit_run_record(run_record)

        parsed_ref = PullRequestRef.parse(pr_ref)
        summary_poster = SummaryPoster(github_client)
        pr_obj = github_client.get_pull_request(parsed_ref)

        if config.features.inline_comments:
            _logger.info("Sink mode: inline + summary")
            comment_body, state = _post_inline_and_render(
                config=config,
                github_client=github_client,
                summary_poster=summary_poster,
                pr_obj=pr_obj,
                parsed_ref=parsed_ref,
                result=result,
                head_sha=head_sha,
                cost_line=cost_line,
            )
        else:
            _logger.info("Sink mode: summary only")
            comment_body = render_comment(result, cost_line=cost_line)
            state = {"last_reviewed_sha": head_sha}

        summary_poster.post(pr_obj, comment_body, state=state)

        _logger.info("Review posted for %s", pr_ref)
        sys.exit(0)

    except BudgetExceededError as exc:
        _logger.error(
            "Review aborted: budget cap exceeded ($%.4f/$%.4f)",
            exc.spent_usd,
            exc.cap_usd,
        )
        emit_run_record(
            {
                "event": "review_failed",
                "error_type": "BudgetExceededError",
                "spent_usd": exc.spent_usd,
                "cap_usd": exc.cap_usd,
            }
        )
        try:
            abort_poster = SummaryPoster(github_client)
            abort_pr = github_client.get_pull_request(PullRequestRef.parse(pr_ref))
            abort_poster.post(
                abort_pr,
                f"Review aborted: budget cap exceeded (${exc.spent_usd:.4f}/${exc.cap_usd:.4f}).",
            )
        except Exception:
            _logger.warning("Failed to post budget-exceeded comment")
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as exc:
        _logger.error("Review failed: %s", type(exc).__name__)
        emit_run_record(
            {
                "event": "review_failed",
                "error_type": type(exc).__name__,
            }
        )
        sys.exit(1)


def _handle_command_event(
    event: dict[str, Any],
    config: LycheeConfig,
    github_client: GitHubClient,
    claude_client: ClaudeClient,
) -> None:
    """Handle an issue_comment event containing an @lychee command.

    Steps:
    1. Extract comment body, author, PR number from the event.
    2. Parse the command via parse_command().
    3. If not a command (None), return silently.
    4. If unknown command, post help text and return.
    5. Check authorization via is_authorized().
    6. If unauthorized, post refusal and return.
    7. Run the review engine.
    8. Render the command-specific response.
    9. Post as an issue comment reply.

    Raises SystemExit(0) on success, SystemExit(1) on failure.
    """
    comment_body: str = event["comment"]["body"]
    user: str = event["comment"]["user"]["login"]
    pr_number: int = event["issue"]["number"]
    repo: str = os.environ["GITHUB_REPOSITORY"]
    pr_ref = f"{repo}#{pr_number}"

    _logger.info("Processing command event from %s on %s", user, pr_ref)

    # Parse the command from the comment body.
    parsed = parse_command(comment_body)

    if parsed is None:
        _logger.info("No @lychee mention in comment; skipping")
        sys.exit(0)

    parsed_ref = PullRequestRef.parse(pr_ref)
    pr_obj = github_client.get_pull_request(parsed_ref)

    if isinstance(parsed, UnknownCommand):
        _logger.info("Unknown command %r from %s; posting help", parsed.raw_text, user)
        pr_obj.create_issue_comment(body=HELP_TEXT)
        sys.exit(0)

    assert isinstance(parsed, ParsedCommand)
    command = parsed.command
    _logger.info("Command: %s from user: %s on %s", command.value, user, pr_ref)

    # Authorization check.
    if not is_authorized(user, config):
        _logger.info("User %s unauthorized for command %s", user, command.value)
        pr_obj.create_issue_comment(body=format_refusal(user))
        sys.exit(0)

    # Run the review engine (same as automatic review path).
    start = time.monotonic()
    result = run_review(pr_ref, config, github_client, claude_client)
    duration = time.monotonic() - start

    cost_usd = compute_cost(result.usage, result.model)
    cost_line: str | None = None
    if config.features.cost_footer:
        cost_line = format_cost_line(cost_usd, result.usage)
    _logger.info("Command review cost: $%.4f", cost_usd)

    run_record = build_run_record(
        repo=repo,
        pr_number=pr_number,
        head_sha="command",
        model=result.model,
        usage=result.usage,
        cost_usd=cost_usd,
        ripeness=result.ripeness.value,
        finding_counts=compute_finding_counts(result.findings),
        duration_seconds=duration,
        review_strategy=get_review_strategy(),
        triage_verdict=get_triage_verdict(),
    )
    run_record["command"] = command.value
    emit_run_record(run_record)

    # Render the command-specific response.
    renderer = COMMAND_RENDERERS[command.value]
    response = renderer(result, cost_line) if command == Command.peel else renderer(result)

    # Post the response as an issue comment.
    pr_obj.create_issue_comment(body=response)

    _logger.info("Command %s response posted for %s", command.value, pr_ref)
    sys.exit(0)


def _is_command_event(event: dict[str, Any]) -> bool:
    """Return True if the event is an issue_comment on a PR with action 'created'."""
    if event.get("action") not in _COMMAND_ACTIONS:
        return False
    issue = event.get("issue")
    if issue is None:
        return False
    # GitHub issue_comment events on PRs have issue.pull_request set.
    return "pull_request" in issue


def _post_inline_and_render(
    *,
    config: Any,
    github_client: GitHubClient,
    summary_poster: SummaryPoster,
    pr_obj: Any,
    parsed_ref: PullRequestRef,
    result: Any,
    head_sha: str,
    cost_line: str | None,
) -> tuple[str, dict[str, Any]]:
    """Post inline comments and render the summary with fallback findings.

    Fetches the diff, extracts previous state for dedup, posts inline
    comments via ``InlineReviewPoster``, and renders the summary comment
    with any unmappable findings folded into the fallback section.

    If inline posting fails, logs the error and falls back to summary-only
    mode so the summary comment is never blocked by an inline failure.

    Returns (comment_body, state) for the caller to pass to
    ``SummaryPoster.post()``.
    """
    try:
        diff = github_client.get_diff(parsed_ref)

        # Extract previous state from existing summary comment for dedup.
        existing_comment = summary_poster._find_existing_comment(pr_obj)
        previous_state: dict[str, Any] | None = None
        if existing_comment is not None:
            previous_state = SummaryPoster.extract_state(existing_comment.body)

        inline_poster = InlineReviewPoster(github_client)
        inline_result = inline_poster.post(
            pr_obj,
            result,
            diff,
            severity_threshold=config.review.severity_threshold,
            previous_state=previous_state,
        )

        _logger.info(
            "Inline posting: %d posted, %d fallback",
            inline_result.inline_count,
            inline_result.fallback_count,
        )

        comment_body = render_comment(
            result,
            cost_line=cost_line,
            severity_threshold=config.review.severity_threshold,
            fallback_findings=inline_result.fallback_findings,
        )

        state: dict[str, Any] = build_inline_state(
            inline_result.posted_findings,
            head_sha=head_sha,
        )
        return comment_body, state

    except PosterError as exc:
        _logger.error("Inline posting failed, falling back to summary only: %s", exc)
        comment_body = render_comment(
            result,
            cost_line=cost_line,
            severity_threshold=config.review.severity_threshold,
        )
        return comment_body, {"last_reviewed_sha": head_sha}


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
