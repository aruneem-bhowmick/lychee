"""CLI entry point for the lychee package."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from lychee.config import load_config
from lychee.review import run_review_dry


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
def review(dry_run: bool, fixture: Path | None) -> None:
    """Run a PR review (Peel).

    In dry-run mode no network calls are made; the rendered comment is
    printed to stdout and the process exits 0.  Pass --fixture to specify
    the PR JSON used as input.
    """
    if dry_run:
        if fixture is None:
            raise click.UsageError("--fixture is required when using --dry-run.")
        config = load_config()
        comment = run_review_dry(fixture_path=fixture, config=config)
        click.echo(comment)
        sys.exit(0)
    else:
        raise click.UsageError(
            "Live review is not yet available. "
            "Use --dry-run with --fixture for offline testing."
        )


if __name__ == "__main__":
    cli()
