"""Comment renderer — converts a ReviewResult to GitHub markdown."""

from lychee.models import ReviewResult


def render_comment(result: ReviewResult, cost_line: str | None = None) -> str:
    """Render a ReviewResult to the comment markdown string.

    Produces a single GitHub PR comment with the hidden lychee:review marker,
    Ripeness badge, Nectar, The Peel, grouped Pits, and optional cost footer.
    """
    ...
