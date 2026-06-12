"""Unit, integration, acceptance, regression, and API tests for lychee.claude.

Covers ClaudeReviewError, ClaudeClient construction, static helpers
(_extract_tool_use, _extract_usage), the review() method with mocked
API responses, and snapshot-based regression tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import anthropic
import anthropic.types
import pytest

from lychee.claude import ClaudeClient, ClaudeReviewError
from lychee.models import ReviewResult

FIXTURES_DIR = Path(__file__).parent / "fixtures"

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


# ---------------------------------------------------------------------------
# Integration tests (mocked API)
# ---------------------------------------------------------------------------


class TestReviewIntegration:
    """Integration tests for ClaudeClient.review() with mocked API."""

    def _make_client(self) -> ClaudeClient:
        """Create a ClaudeClient with a mocked Anthropic client."""
        client = ClaudeClient(api_key="sk-test", model="claude-sonnet-4-6")
        client._client = MagicMock(spec=anthropic.Anthropic)
        return client

    def test_review_success(self) -> None:
        """review() returns a valid ReviewResult on a well-formed response."""
        client = self._make_client()
        client._client.messages.create.return_value = _make_message()

        result = client.review(messages=[{"role": "user", "content": "Review this PR."}])

        assert result.ripeness.value == "ripe"
        assert result.summary == "Looks good."
        assert result.model == "claude-sonnet-4-6"

    def test_review_injects_model_and_usage(self) -> None:
        """review() injects model name and extracted usage into the ReviewResult."""
        client = self._make_client()
        usage = _make_usage(input_tokens=500, output_tokens=200)
        client._client.messages.create.return_value = _make_message(usage=usage)

        result = client.review(messages=[{"role": "user", "content": "Review."}])

        assert result.model == "claude-sonnet-4-6"
        assert result.usage["input_tokens"] == 500
        assert result.usage["output_tokens"] == 200

    def test_review_passes_system_prompt(self) -> None:
        """review() passes the system parameter to messages.create when provided."""
        client = self._make_client()
        client._client.messages.create.return_value = _make_message()

        client.review(
            messages=[{"role": "user", "content": "Review."}],
            system="You are a code reviewer.",
        )

        call_kwargs = client._client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == "You are a code reviewer."

    def test_review_omits_system_when_none(self) -> None:
        """review() does not pass system key when system is None."""
        client = self._make_client()
        client._client.messages.create.return_value = _make_message()

        client.review(messages=[{"role": "user", "content": "Review."}])

        call_kwargs = client._client.messages.create.call_args
        assert "system" not in call_kwargs.kwargs

    def test_review_forces_tool_choice(self) -> None:
        """review() forces tool_choice to submit_review."""
        client = self._make_client()
        client._client.messages.create.return_value = _make_message()

        client.review(messages=[{"role": "user", "content": "Review."}])

        call_kwargs = client._client.messages.create.call_args
        assert call_kwargs.kwargs["tool_choice"] == {
            "type": "tool",
            "name": "submit_review",
        }

    def test_review_api_error_raises(self) -> None:
        """review() wraps anthropic.APIError into ClaudeReviewError."""
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {}
        client._client.messages.create.side_effect = anthropic.APIStatusError(
            message="Internal Server Error",
            response=mock_response,
            body=None,
        )

        with pytest.raises(ClaudeReviewError, match="API error"):
            client.review(messages=[{"role": "user", "content": "Review."}])

    def test_review_connection_error_raises(self) -> None:
        """review() wraps anthropic.APIConnectionError into ClaudeReviewError."""
        client = self._make_client()
        client._client.messages.create.side_effect = anthropic.APIConnectionError(
            request=MagicMock(),
        )

        with pytest.raises(ClaudeReviewError, match="API connection error"):
            client.review(messages=[{"role": "user", "content": "Review."}])

    def test_review_invalid_tool_input_raises(self) -> None:
        """review() wraps pydantic.ValidationError into ClaudeReviewError."""
        client = self._make_client()
        # Tool input with invalid ripeness value
        bad_input = _make_tool_input(ripeness="invalid_value")
        message = _make_message(content=[_make_tool_use_block(bad_input)])
        client._client.messages.create.return_value = message

        with pytest.raises(ClaudeReviewError, match="Invalid tool input"):
            client.review(messages=[{"role": "user", "content": "Review."}])

    def test_review_no_tool_block_raises(self) -> None:
        """review() raises ClaudeReviewError when response has no tool_use block."""
        client = self._make_client()
        message = _make_message(content=[_make_text_block()])
        client._client.messages.create.return_value = message

        with pytest.raises(ClaudeReviewError, match="No tool_use block found"):
            client.review(messages=[{"role": "user", "content": "Review."}])


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


class TestAcceptance:
    """End-to-end-style acceptance tests with mocked API."""

    def _make_client(self) -> ClaudeClient:
        """Create a ClaudeClient with a mocked Anthropic client."""
        client = ClaudeClient(api_key="sk-test", model="claude-sonnet-4-6")
        client._client = MagicMock(spec=anthropic.Anthropic)
        return client

    def test_accept_mocked_tool_response_parses(self) -> None:
        """A realistic mocked tool response parses into a valid ReviewResult."""
        tool_input = _make_tool_input(
            findings=[
                {
                    "file": "src/main.py",
                    "line": 10,
                    "severity": "minor",
                    "category": "style",
                    "message": "Consider renaming this variable.",
                }
            ],
        )
        client = self._make_client()
        message = _make_message(
            content=[_make_text_block(), _make_tool_use_block(tool_input)],
        )
        client._client.messages.create.return_value = message

        result = client.review(messages=[{"role": "user", "content": "Review."}])

        assert result.ripeness.value == "ripe"
        assert len(result.findings) == 1
        assert result.findings[0].file == "src/main.py"
        assert result.findings[0].severity.value == "minor"

    def test_accept_malformed_response_raises_typed_error(self) -> None:
        """A malformed tool response raises ClaudeReviewError, not a generic exception."""
        client = self._make_client()
        bad_input = {"ripeness": "invalid", "summary": "", "walkthrough": "", "findings": []}
        message = _make_message(content=[_make_tool_use_block(bad_input)])
        client._client.messages.create.return_value = message

        with pytest.raises(ClaudeReviewError):
            client.review(messages=[{"role": "user", "content": "Review."}])

    def test_accept_usage_captured(self) -> None:
        """Token usage from the API response is captured in the ReviewResult."""
        client = self._make_client()
        usage = _make_usage(
            input_tokens=1200,
            output_tokens=300,
            cache_read_input_tokens=800,
        )
        client._client.messages.create.return_value = _make_message(usage=usage)

        result = client.review(messages=[{"role": "user", "content": "Review."}])

        assert result.usage["input_tokens"] == 1200
        assert result.usage["output_tokens"] == 300
        assert result.usage["cache_read_input_tokens"] == 800


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


class TestRegression:
    """Regression tests to guard against unintended changes."""

    def _make_client(self) -> ClaudeClient:
        """Create a ClaudeClient with a mocked Anthropic client."""
        client = ClaudeClient(api_key="sk-test", model="claude-sonnet-4-6")
        client._client = MagicMock(spec=anthropic.Anthropic)
        return client

    def test_tool_schema_used_in_call(self) -> None:
        """review() passes the ReviewResult tool schema to the API call."""
        client = self._make_client()
        client._client.messages.create.return_value = _make_message()

        client.review(messages=[{"role": "user", "content": "Review."}])

        call_kwargs = client._client.messages.create.call_args
        tools = call_kwargs.kwargs["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "submit_review"
        assert "input_schema" in tools[0]

    def test_review_result_fields_snapshot(self) -> None:
        """ReviewResult from a mocked review matches the pinned fixture snapshot."""
        client = self._make_client()
        client._client.messages.create.return_value = _make_message()

        result = client.review(messages=[{"role": "user", "content": "Review."}])

        snapshot_path = FIXTURES_DIR / "claude_review_result_snapshot.json"
        expected = json.loads(snapshot_path.read_text(encoding="utf-8"))
        actual = result.model_dump()
        assert actual == expected, (
            "ReviewResult snapshot mismatch. If intentional, update "
            "tests/fixtures/claude_review_result_snapshot.json."
        )


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


class TestAPI:
    """Tests verifying the shape of API call parameters."""

    def _make_client(self) -> ClaudeClient:
        """Create a ClaudeClient with a mocked Anthropic client."""
        client = ClaudeClient(api_key="sk-test", model="claude-sonnet-4-6")
        client._client = MagicMock(spec=anthropic.Anthropic)
        return client

    def test_api_messages_create_params(self) -> None:
        """messages.create is called with expected parameters."""
        client = self._make_client()
        client._client.messages.create.return_value = _make_message()

        client.review(
            messages=[{"role": "user", "content": "Review."}],
            system="Be concise.",
        )

        call_kwargs = client._client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-6"
        assert call_kwargs["max_tokens"] == 4096
        assert call_kwargs["messages"] == [{"role": "user", "content": "Review."}]
        assert call_kwargs["system"] == "Be concise."
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "submit_review"}
        assert len(call_kwargs["tools"]) == 1

    def test_api_tool_schema_shape(self) -> None:
        """The tool schema passed to the API has the expected structure."""
        schema = ReviewResult.to_tool_schema()
        assert schema["name"] == "submit_review"
        assert "description" in schema
        assert "input_schema" in schema
        props = schema["input_schema"]["properties"]
        for field in ("ripeness", "summary", "walkthrough", "findings"):
            assert field in props, f"Missing field '{field}' in tool schema"
