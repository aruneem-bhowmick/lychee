"""Review engine — orchestrates context fetch, prompt construction, and Claude call."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from lychee.claude import ClaudeClient
from lychee.config import LycheeConfig
from lychee.github_client import GitHubClient
from lychee.models import ReviewResult
from lychee.render import render_comment

_logger = logging.getLogger(__name__)

# Resolved relative to this file: src/lychee/review.py → src/lychee → src → project root
_PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
_BUNDLED_RESULT_PATH: Path = (
    _PROJECT_ROOT / "tests" / "fixtures" / "review_result_ripe.json"
)


def run_review(
    pr_ref: str,
    config: LycheeConfig,
    github_client: GitHubClient,
    claude_client: ClaudeClient,
) -> ReviewResult:
    """Orchestrate fetch → prompt → Claude → ReviewResult."""
    raise NotImplementedError("run_review not implemented")


def run_review_dry(
    fixture_path: Path,
    config: LycheeConfig,
) -> str:
    """Run the review engine end-to-end from a fixture, with no network I/O.

    Loads the PR fixture from `fixture_path`, loads the expected ReviewResult
    from the sidecar `review_result_ripe.json` in the same directory (falling
    back to the bundled fixture when absent), renders the comment, and returns
    it as a string.

    The PR fixture content is validated as JSON but otherwise treated as opaque;
    only the ReviewResult fixture drives the rendered output.

    Raises FileNotFoundError if `fixture_path` does not exist.
    Raises ValueError if the fixture cannot be parsed as valid JSON.
    Raises pydantic.ValidationError if the ReviewResult fixture is malformed.
    """
    _logger.debug("run_review_dry: loading fixture from %s", fixture_path)

    # Validate that the PR fixture is well-formed JSON (content is not used further).
    try:
        json.loads(fixture_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid fixture JSON at {fixture_path}: {exc}") from exc

    # Locate the companion ReviewResult fixture.
    # Dry-run always uses the ripe fixture; live mode replaces this with a Claude call.
    result_path: Path = fixture_path.parent / "review_result_ripe.json"
    if not result_path.exists():
        result_path = _BUNDLED_RESULT_PATH

    result_data: dict[str, Any] = json.loads(result_path.read_text(encoding="utf-8"))
    result: ReviewResult = ReviewResult.from_tool_input(result_data)

    return render_comment(result, cost_line=None)
