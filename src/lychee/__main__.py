"""CLI entry point for the lychee package."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

from lychee.claude import ClaudeClient
from lychee.config import load_config
from lychee.github_client import GitHubClient, PullRequestRef
from lychee.poster import SummaryPoster
from lychee.render import render_comment
from lychee.review import run_review, run_review_dry


@click.group()
def cli() -> None:
    """Lychee — peel back your pull requests."""


@cli.command()
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Run without network I/O, using a fixture file.",
)
@click.option(
    "--fixture",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to fixture PR JSON (required with --dry-run).",
)
@click.option(
    "--pr",
    type=str,
    default=None,
    help="PR reference (owner/repo#number).",
)
@click.option(
    "--post/--no-post",
    default=True,
    help="Post the comment to GitHub (default: yes).",
)
def review(dry_run: bool, fixture: Path | None, pr: str | None, post: bool) -> None:
    """Run a PR review (Peel).

    Dry-run mode: --dry-run --fixture <f> (no network, prints to stdout).
    Live mode: --pr owner/repo#123 (requires GITHUB_TOKEN and ANTHROPIC_API_KEY env vars).
    """
    if dry_run:
        if fixture is None:
            raise click.UsageError("--fixture is required when using --dry-run.")
        config = load_config()
        comment = run_review_dry(fixture_path=fixture, config=config)
        click.echo(comment)
        sys.exit(0)

    if pr is None:
        raise click.UsageError(
            "Either --dry-run --fixture <path> or --pr <owner/repo#number> is required."
        )

    # Live review path
    github_token = os.environ.get("GITHUB_TOKEN")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if not github_token:
        raise click.UsageError("GITHUB_TOKEN environment variable is required for live review.")
    if not anthropic_key:
        raise click.UsageError(
            "ANTHROPIC_API_KEY environment variable is required for live review."
        )

    config = load_config()
    github_client = GitHubClient(token=github_token)
    claude_client = ClaudeClient(api_key=anthropic_key, model=config.model.default)

    result = run_review(pr, config, github_client, claude_client)

    cost_line: str | None = None  # Cost footer computation deferred
    comment_body = render_comment(result, cost_line=cost_line)

    if post:
        poster = SummaryPoster(github_client)
        pr_obj = github_client.get_pull_request(PullRequestRef.parse(pr))
        poster.post(pr_obj, comment_body)
        click.echo(f"Review posted for {pr}")
    else:
        click.echo(comment_body)


if __name__ == "__main__":
    cli()
