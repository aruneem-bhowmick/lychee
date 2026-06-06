"""Prompt construction for the Anthropic Messages API."""

from typing import Any

from lychee.config import LycheeConfig
from lychee.context import ReviewContext


def build_messages(context: ReviewContext, config: LycheeConfig) -> list[dict[str, Any]]:
    """Construct the Anthropic Messages API payload for a PR review."""
    raise NotImplementedError("build_messages not implemented")
