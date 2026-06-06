"""Anthropic SDK wrapper for tool-use PR reviews."""

from lychee.models import ReviewResult


class ClaudeClient:
    """Wraps the Anthropic SDK for tool-use reviews."""

    def __init__(self, api_key: str, model: str) -> None:
        """Initialise the client with an API key and model identifier."""
        raise NotImplementedError("ClaudeClient.__init__ not implemented")

    def review(self, messages: list[object]) -> ReviewResult:
        """Send messages to Claude and return a parsed ReviewResult."""
        raise NotImplementedError("ClaudeClient.review not implemented")
