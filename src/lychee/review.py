"""Review engine — orchestrates context fetch, prompt construction, and Claude call."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from lychee.claude import ClaudeClient
from lychee.config import LycheeConfig
from lychee.context import ReviewContext, build_context
from lychee.github_client import GitHubClient, PullRequestRef
from lychee.models import ReviewResult
from lychee.prompt import (
    build_map_user_message,
    build_messages,
    build_reduce_user_message,
    build_system_prompt_blocks,
)
from lychee.render import render_comment

_logger = logging.getLogger(__name__)

# Resolved relative to this file: src/lychee/review.py → src/lychee → src → project root
_PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
_BUNDLED_RESULT_PATH: Path = _PROJECT_ROOT / "tests" / "fixtures" / "review_result_ripe.json"

_LARGE_PR_THRESHOLD: int = 100_000

_MAP_GROUP_SIZE: int = 10
_MAP_REDUCE_FILE_THRESHOLD: int = 50


def _compute_context_size(context: ReviewContext) -> int:
    """Compute the total context size in characters from diff and file contents."""
    total = len(context.diff)
    for f in context.changed_files:
        content: str | None = f.get("content_at_head")
        if content is not None:
            total += len(content)
    return total


def select_model(config: LycheeConfig, context_size: int) -> str:
    """Pick the model based on context size: large_pr if above threshold, else default."""
    if context_size > _LARGE_PR_THRESHOLD:
        return config.model.large_pr
    return config.model.default


def _should_map_reduce(context: ReviewContext, config: LycheeConfig) -> bool:
    """Return True when the PR has more files than the configured threshold.

    Uses ``config.review.max_files`` (default 50) as an exclusive threshold:
    map-reduce is triggered only when ``len(context.changed_files) > max_files``.
    """
    return len(context.changed_files) > config.review.max_files


def _partition_files(
    changed_files: list[dict[str, Any]],
    group_size: int,
) -> list[list[dict[str, Any]]]:
    """Split *changed_files* into chunks of at most *group_size*, preserving order."""
    return [changed_files[i : i + group_size] for i in range(0, len(changed_files), group_size)]


def _filter_diff_for_files(diff: str, filenames: set[str]) -> str:
    """Return only the sections of a unified diff that match *filenames*.

    Splits the diff on ``diff --git`` headers and keeps sections whose
    ``a/`` or ``b/`` path is in *filenames*.  Returns an empty string when
    no sections match or either input is empty.
    """
    if not diff or not filenames:
        return ""

    sections: list[str] = []
    current: list[str] = []
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current:
                sections.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("".join(current))

    kept: list[str] = []
    for section in sections:
        header = section.split("\n", 1)[0]
        # header looks like: diff --git a/path b/path
        parts = header.split()
        if len(parts) >= 4:
            a_path = parts[2].removeprefix("a/")
            b_path = parts[3].removeprefix("b/")
            if a_path in filenames or b_path in filenames:
                kept.append(section)
    return "".join(kept)


def _aggregate_usage(
    partial_results: list[ReviewResult],
    reduce_result: ReviewResult,
) -> dict[str, Any]:
    """Sum all integer-valued usage fields across map partials and the reduce result."""
    totals: dict[str, int] = {}
    for result in [*partial_results, reduce_result]:
        for key, value in result.usage.items():
            if isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
    return totals


def _run_map_phase(
    context: ReviewContext,
    groups: list[list[dict[str, Any]]],
    config: LycheeConfig,
    claude_client: ClaudeClient,
    system: list[dict[str, Any]],
    model_override: str,
) -> list[ReviewResult]:
    """Execute the map phase: review each file group sequentially.

    Returns a list of partial ReviewResults.  If every group fails, raises
    ``ClaudeReviewError``.  Partial failures are logged and skipped.
    """
    from lychee.claude import ClaudeReviewError

    partial_results: list[ReviewResult] = []
    errors: list[Exception] = []

    for i, group in enumerate(groups):
        _logger.info("Map phase: reviewing group %d/%d (%d files)", i + 1, len(groups), len(group))
        user_msg = build_map_user_message(context, group, i, len(groups))
        messages = [{"role": "user", "content": user_msg}]
        try:
            result = claude_client.review(messages, system=system, model_override=model_override)
            partial_results.append(result)
        except Exception as exc:
            _logger.warning("Map phase group %d/%d failed: %s", i + 1, len(groups), exc)
            errors.append(exc)

    if not partial_results:
        raise ClaudeReviewError(
            f"Map phase failed: all {len(groups)} groups failed. "
            f"First error: {errors[0] if errors else 'unknown'}"
        )

    if errors:
        _logger.warning(
            "Map phase: %d/%d groups failed, continuing with %d partial results",
            len(errors),
            len(groups),
            len(partial_results),
        )

    return partial_results


def _run_reduce_phase(
    context: ReviewContext,
    partial_results: list[ReviewResult],
    config: LycheeConfig,
    claude_client: ClaudeClient,
    system: list[dict[str, Any]],
    model_override: str,
) -> ReviewResult:
    """Execute the reduce phase: merge partial results into a single ReviewResult.

    Builds a reduce prompt from the partial results, calls Claude, and
    replaces the usage dict with aggregated totals from all phases.
    """
    partial_dicts = [r.model_dump() for r in partial_results]
    user_msg = build_reduce_user_message(context, partial_dicts)
    messages = [{"role": "user", "content": user_msg}]

    reduce_result = claude_client.review(messages, system=system, model_override=model_override)
    aggregated_usage = _aggregate_usage(partial_results, reduce_result)

    return reduce_result.model_copy(update={"usage": aggregated_usage})


def run_review(
    pr_ref: str,
    config: LycheeConfig,
    github_client: GitHubClient,
    claude_client: ClaudeClient,
) -> ReviewResult:
    """Orchestrate context fetch, prompt build, and Claude call to produce a ReviewResult.

    For large PRs (more files than ``config.review.max_files``), uses a
    map-reduce strategy: files are partitioned into groups, each reviewed
    individually, then partial results are merged into a single ReviewResult.
    Small PRs continue to use the existing single-pass path unchanged.

    Raises:
    - ValueError if pr_ref is malformed.
    - github.GithubException on GitHub API failures (from context fetcher).
    - ClaudeReviewError on Claude API failures (from Claude client).
    - pydantic.ValidationError if the ReviewResult is somehow malformed.

    Logs a structured info record on completion: PR reference, model,
    ripeness, finding count, usage.
    """
    parsed_ref = PullRequestRef.parse(pr_ref)
    context = build_context(github_client, parsed_ref, config)
    system = build_system_prompt_blocks(config, conventions=context.conventions)

    context_size = _compute_context_size(context)
    model_override = select_model(config, context_size)
    _logger.info(
        "Model selection: context_size=%d threshold=%d selected=%s",
        context_size,
        _LARGE_PR_THRESHOLD,
        model_override,
    )

    if _should_map_reduce(context, config):
        groups = _partition_files(context.changed_files, _MAP_GROUP_SIZE)
        _logger.info(
            "Map-reduce mode: %d files → %d groups of ≤%d",
            len(context.changed_files),
            len(groups),
            _MAP_GROUP_SIZE,
        )
        partial_results = _run_map_phase(
            context, groups, config, claude_client, system, model_override
        )
        result = _run_reduce_phase(
            context, partial_results, config, claude_client, system, model_override
        )
    else:
        messages = build_messages(context, config)
        result = claude_client.review(messages, system=system, model_override=model_override)

    _logger.info(
        "Review complete: pr=%s model=%s ripeness=%s findings=%d usage=%s",
        pr_ref,
        result.model,
        result.ripeness.value,
        len(result.findings),
        result.usage,
    )

    return result


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
