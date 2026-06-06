"""Review engine — orchestrates context fetch, prompt construction, and Claude invocation."""

from lychee.claude import ClaudeClient
from lychee.config import LycheeConfig
from lychee.github_client import GitHubClient
from lychee.models import ReviewResult


def run_review(
    pr_ref: str,
    config: LycheeConfig,
    github_client: GitHubClient,
    claude_client: ClaudeClient,
) -> ReviewResult:
    """Orchestrate fetch → prompt → Claude → ReviewResult."""
    raise NotImplementedError("run_review not implemented")
