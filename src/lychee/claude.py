"""Anthropic SDK wrapper for tool-use PR reviews."""

from __future__ import annotations

import logging
from typing import Any

import anthropic

from lychee.models import ReviewResult

logger = logging.getLogger(__name__)


class ClaudeReviewError(Exception):
    """Raised when the Claude API call or response parsing fails."""


class ClaudeClient:
    """Wraps the Anthropic SDK for tool-use reviews."""

    def __init__(self, api_key: str, model: str) -> None:
        """Initialise the client with an API key and model identifier."""
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    @staticmethod
    def _extract_tool_use(response: anthropic.types.Message) -> dict[str, Any]:
        """Extract the tool-use input dict from the first tool_use content block.

        Raises ClaudeReviewError if no tool_use block is found or the tool
        name is not ``submit_review``.
        """
        for block in response.content:
            if block.type == "tool_use":
                if block.name != "submit_review":
                    raise ClaudeReviewError(
                        f"Unexpected tool name '{block.name}'; expected 'submit_review'"
                    )
                return dict(block.input)
        raise ClaudeReviewError("No tool_use block found in response")

    @staticmethod
    def _extract_usage(response: anthropic.types.Message) -> dict[str, int]:
        """Extract token usage from the response.

        Always includes ``input_tokens`` and ``output_tokens``.
        Includes ``cache_creation_input_tokens`` and
        ``cache_read_input_tokens`` when present and non-zero.
        """
        usage: dict[str, int] = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        cache_creation: int | None = getattr(response.usage, "cache_creation_input_tokens", None)
        if cache_creation:
            usage["cache_creation_input_tokens"] = cache_creation
        cache_read: int | None = getattr(response.usage, "cache_read_input_tokens", None)
        if cache_read:
            usage["cache_read_input_tokens"] = cache_read
        return usage

    def review(self, messages: list[dict[str, Any]], system: str | None = None) -> ReviewResult:
        """Send messages to Claude and return a parsed ReviewResult."""
        raise NotImplementedError("ClaudeClient.review not implemented")
