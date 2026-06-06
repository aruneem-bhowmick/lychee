"""CLI entry point for the lychee package."""

import click


@click.group()
def cli() -> None:
    """Lychee — peel back your pull requests."""


@cli.command()
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Run without network I/O.",
)
@click.option(
    "--fixture",
    type=click.Path(exists=True),
    default=None,
    help="Path to fixture PR JSON.",
)
def review(dry_run: bool, fixture: str | None) -> None:
    """Run a PR review (Peel)."""
    raise NotImplementedError


if __name__ == "__main__":
    cli()
