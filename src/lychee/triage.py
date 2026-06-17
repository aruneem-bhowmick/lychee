"""Triage pre-pass for lightweight PR classification.

Provides an optional Haiku-based pre-pass that classifies PRs as trivial
or substantive before the full review. Trivial PRs (typo fixes, dependency
bumps, config-only changes) take a cheap Haiku-only review path, while
substantive PRs escalate to the full default/large model review.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

import anthropic
import pydantic

from lychee.claude import ClaudeClient, ClaudeReviewError
from lychee.config import LycheeConfig
from lychee.context import ReviewContext
from lychee.models import ReviewResult
from lychee.prompt import build_system_prompt_blocks

_logger = logging.getLogger(__name__)

_TRIAGE_SYSTEM_PROMPT = (
    "You are a PR triage classifier. Analyze the PR and classify it as:\n"
    '- "trivial": Typo fixes, dependency version bumps, config-only changes, '
    "documentation-only changes, formatting-only changes, simple renames.\n"
    '- "substantive": New features, bug fixes, refactoring, security changes, '
    "API changes, logic modifications, test additions/modifications.\n\n"
    "Call the classify_pr tool with your verdict and a one-sentence reason."
)

_MAX_BODY_CHARS = 500
_MAX_DIFF_CHARS = 2000


class TriageVerdict(StrEnum):
    """Classification from the triage pre-pass."""

    trivial = "trivial"
    substantive = "substantive"


class TriageResult:
    """Result of the triage pre-pass."""

    def __init__(self, verdict: TriageVerdict, reason: str) -> None:
        """Store the triage verdict and its justification."""
        self.verdict = verdict
        self.reason = reason

    @property
    def is_trivial(self) -> bool:
        """Return True when the PR was classified as trivial."""
        return self.verdict == TriageVerdict.trivial


def build_triage_prompt(context: ReviewContext) -> tuple[str, list[dict[str, Any]]]:
    """Build a lightweight system prompt and messages for triage classification.

    Returns (system_prompt, messages) tuple.
    The system prompt instructs the model to classify the PR as trivial or substantive.
    The user message includes PR title, truncated body, file list, and condensed diff.
    """
    # Build a lightweight user message with just enough info for classification
    parts: list[str] = []

    parts.append(f"PR Title: {context.pr_title}")

    if context.pr_body:
        truncated_body = context.pr_body[:_MAX_BODY_CHARS]
        if len(context.pr_body) > _MAX_BODY_CHARS:
            truncated_body += "..."
        parts.append(f"PR Body: {truncated_body}")

    # File list (names only, no content)
    if context.changed_files:
        filenames = [f["filename"] for f in context.changed_files]
        parts.append("Changed files:\n" + "\n".join(f"- {name}" for name in filenames))

    # Condensed diff summary (first 2000 chars)
    if context.diff:
        truncated_diff = context.diff[:_MAX_DIFF_CHARS]
        if len(context.diff) > _MAX_DIFF_CHARS:
            truncated_diff += "\n... (diff truncated)"
        parts.append(f"Diff summary:\n```\n{truncated_diff}\n```")

    user_message = "\n\n".join(parts)
    messages = [{"role": "user", "content": user_message}]

    return _TRIAGE_SYSTEM_PROMPT, messages


def build_triage_tool_schema() -> dict[str, Any]:
    """Return the tool schema for the triage classification tool.

    Tool name: 'classify_pr'
    Input schema: {verdict: "trivial"|"substantive", reason: str}
    """
    return {
        "name": "classify_pr",
        "description": "Classify a PR as trivial or substantive.",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["trivial", "substantive"],
                },
                "reason": {
                    "type": "string",
                },
            },
            "required": ["verdict", "reason"],
        },
    }


def run_triage(
    context: ReviewContext,
    claude_client: ClaudeClient,
    config: LycheeConfig,
) -> TriageResult:
    """Run the triage pre-pass on a PR context.

    Calls Claude Haiku with a lightweight prompt to classify the PR.
    Returns a TriageResult with the verdict and reason.
    On error, defaults to 'substantive' (fail-safe: always escalate on failure).
    """
    try:
        system_prompt, messages = build_triage_prompt(context)
        tool = build_triage_tool_schema()
        triage_model = config.model.triage

        response = claude_client._client.messages.create(
            model=triage_model,
            max_tokens=256,
            system=system_prompt,
            messages=messages,
            tools=[tool],
            tool_choice={"type": "tool", "name": "classify_pr"},
        )

        # Extract the tool-use block
        tool_input: dict[str, Any] | None = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "classify_pr":
                tool_input = dict(block.input)
                break

        if tool_input is None:
            _logger.warning("Triage: no classify_pr tool call in response, defaulting to substantive")
            return TriageResult(TriageVerdict.substantive, "No classification returned by model")

        verdict = TriageVerdict(tool_input["verdict"])
        reason = tool_input.get("reason", "")

        result = TriageResult(verdict, reason)
        _logger.info(
            "Triage verdict: %s (reason: %s)",
            result.verdict.value,
            result.reason,
        )
        return result

    except Exception as exc:
        _logger.warning("Triage failed, defaulting to substantive: %s", exc)
        return TriageResult(TriageVerdict.substantive, f"Triage error: {exc}")


def run_trivial_review(
    context: ReviewContext,
    claude_client: ClaudeClient,
    config: LycheeConfig,
) -> ReviewResult:
    """Run a lightweight review for a trivially-classified PR.

    Uses the triage model (Haiku) with the full review prompt and tool schema
    to produce a complete ReviewResult. Typically produces a 'ripe' verdict
    with few or no findings.
    """
    system = build_system_prompt_blocks(config, conventions=context.conventions)
    from lychee.prompt import build_messages

    messages = build_messages(context, config)
    triage_model = config.model.triage

    _logger.info("Running trivial review with model %s", triage_model)
    return claude_client.review(messages, system=system, model_override=triage_model)
