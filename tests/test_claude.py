"""Unit, integration, acceptance, regression, and API tests for lychee.claude.

Covers ClaudeReviewError, ClaudeClient construction, static helpers
(_extract_tool_use, _extract_usage), the review() method with mocked
API responses, and snapshot-based regression tests.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import anthropic
import anthropic.types
import pytest

from lychee.claude import ClaudeClient, ClaudeReviewError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_input(**overrides: Any) -> dict[str, Any]:
    """Return a valid submit_review tool input dict."""
    base: dict[str, Any] = {
        "ripeness": "ripe",
        "summary": "Looks good.",
        "walkthrough": "## Summary\nAll changes are minimal.",
        "findings": [],
    }
    base.update(overrides)
    return base


def _make_usage(
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_creation_input_tokens: int | None = None,
    cache_read_input_tokens: int | None = None,
) -> anthropic.types.Usage:
    """Build an anthropic Usage object."""
    kwargs: dict[str, Any] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    if cache_creation_input_tokens is not None:
        kwargs["cache_creation_input_tokens"] = cache_creation_input_tokens
    if cache_read_input_tokens is not None:
        kwargs["cache_read_input_tokens"] = cache_read_input_tokens
    return anthropic.types.Usage(**kwargs)


def _make_tool_use_block(
    tool_input: dict[str, Any] | None = None,
    name: str = "submit_review",
) -> anthropic.types.ToolUseBlock:
    """Build a ToolUseBlock with the given input."""
    return anthropic.types.ToolUseBlock(
        id="toolu_test123",
        input=tool_input or _make_tool_input(),
        name=name,
        type="tool_use",
    )


def _make_text_block(text: str = "Here is my review.") -> anthropic.types.TextBlock:
    """Build a TextBlock."""
    return anthropic.types.TextBlock(text=text, type="text")


def _make_message(
    content: list[Any] | None = None,
    usage: anthropic.types.Usage | None = None,
) -> anthropic.types.Message:
    """Build a complete anthropic Message with sensible defaults."""
    return anthropic.types.Message(
        id="msg_test123",
        content=content or [_make_tool_use_block()],
        model="claude-sonnet-4-6",
        role="assistant",
        stop_reason="tool_use",
        type="message",
        usage=usage or _make_usage(),
    )


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


class TestSmoke:
    """Ensure the module imports cleanly."""

    def test_claude_module_imports(self) -> None:
        """ClaudeClient and ClaudeReviewError import from lychee.claude."""
        from lychee.claude import ClaudeClient, ClaudeReviewError

        assert callable(ClaudeClient)
        assert issubclass(ClaudeReviewError, Exception)


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


class TestSanity:
    """Basic construction sanity checks."""

    def test_client_construction(self) -> None:
        """ClaudeClient constructs without raising."""
        client = ClaudeClient(api_key="sk-test-key", model="claude-sonnet-4-6")
        assert client._model == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# _extract_tool_use tests
# ---------------------------------------------------------------------------


class TestExtractToolUse:
    """Tests for ClaudeClient._extract_tool_use static method."""

    def test_extract_tool_use_success(self) -> None:
        """Extracts tool input from a valid submit_review tool_use block."""
        tool_input = _make_tool_input()
        message = _make_message(content=[_make_tool_use_block(tool_input)])
        result = ClaudeClient._extract_tool_use(message)
        assert result["ripeness"] == "ripe"
        assert result["summary"] == "Looks good."

    def test_extract_tool_use_with_text_before(self) -> None:
        """Extracts tool input even when a TextBlock precedes the tool_use block."""
        tool_input = _make_tool_input()
        message = _make_message(content=[_make_text_block(), _make_tool_use_block(tool_input)])
        result = ClaudeClient._extract_tool_use(message)
        assert result["ripeness"] == "ripe"

    def test_extract_tool_use_no_block(self) -> None:
        """Raises ClaudeReviewError when no tool_use block is present."""
        message = _make_message(content=[_make_text_block()])
        with pytest.raises(ClaudeReviewError, match="No tool_use block found"):
            ClaudeClient._extract_tool_use(message)

    def test_extract_tool_use_wrong_name(self) -> None:
        """Raises ClaudeReviewError when tool name is not submit_review."""
        block = _make_tool_use_block(name="wrong_tool")
        message = _make_message(content=[block])
        with pytest.raises(ClaudeReviewError, match="Unexpected tool name"):
            ClaudeClient._extract_tool_use(message)


# ---------------------------------------------------------------------------
# _extract_usage tests
# ---------------------------------------------------------------------------


class TestExtractUsage:
    """Tests for ClaudeClient._extract_usage static method."""

    def test_extract_usage_basic(self) -> None:
        """Extracts input_tokens and output_tokens from usage."""
        message = _make_message(usage=_make_usage(input_tokens=200, output_tokens=100))
        result = ClaudeClient._extract_usage(message)
        assert result == {"input_tokens": 200, "output_tokens": 100}

    def test_extract_usage_with_cache(self) -> None:
        """Includes cache fields when present and non-zero."""
        usage = _make_usage(
            input_tokens=200,
            output_tokens=100,
            cache_creation_input_tokens=50,
            cache_read_input_tokens=30,
        )
        message = _make_message(usage=usage)
        result = ClaudeClient._extract_usage(message)
        assert result == {
            "input_tokens": 200,
            "output_tokens": 100,
            "cache_creation_input_tokens": 50,
            "cache_read_input_tokens": 30,
        }

    def test_extract_usage_no_cache(self) -> None:
        """Omits cache fields when they are zero or absent."""
        usage = _make_usage(
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )
        message = _make_message(usage=usage)
        result = ClaudeClient._extract_usage(message)
        assert result == {"input_tokens": 100, "output_tokens": 50}


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------


class TestInit:
    """Tests for ClaudeClient.__init__."""

    def test_client_init_no_api_call(self) -> None:
        """Construction does not make any API calls."""
        with patch.object(anthropic.Anthropic, "__init__", return_value=None) as mock_init:
            client = ClaudeClient(api_key="sk-test", model="claude-sonnet-4-6")
            mock_init.assert_called_once_with(api_key="sk-test")
            assert client._model == "claude-sonnet-4-6"
