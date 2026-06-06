"""Review engine — orchestrates context fetch, prompt construction, and Claude invocation."""

from lychee.models import ReviewResult


def run_review(
    pr_ref: str,
    config: object,
    github_client: object,
    claude_client: object,
) -> ReviewResult:
    """Orchestrate fetch → prompt → Claude → ReviewResult."""
    ...
