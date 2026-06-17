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
from lychee.rate_limiter import RetryConfig, TokenBucketLimiter

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

    def _make_client(self) -> tuple[ClaudeClient, MagicMock]:
        """Create a ClaudeClient with a mocked Anthropic client."""
        client = ClaudeClient(api_key="sk-test", model="claude-sonnet-4-6")
        mock_api = MagicMock()
        client._client = mock_api  # type: ignore[assignment]
        return client, mock_api

    def test_review_success(self) -> None:
        """review() returns a valid ReviewResult on a well-formed response."""
        client, mock_api = self._make_client()
        mock_api.messages.create.return_value = _make_message()

        result = client.review(messages=[{"role": "user", "content": "Review this PR."}])

        assert result.ripeness.value == "ripe"
        assert result.summary == "Looks good."
        assert result.model == "claude-sonnet-4-6"

    def test_review_injects_model_and_usage(self) -> None:
        """review() injects model name and extracted usage into the ReviewResult."""
        client, mock_api = self._make_client()
        usage = _make_usage(input_tokens=500, output_tokens=200)
        mock_api.messages.create.return_value = _make_message(usage=usage)

        result = client.review(messages=[{"role": "user", "content": "Review."}])

        assert result.model == "claude-sonnet-4-6"
        assert result.usage["input_tokens"] == 500
        assert result.usage["output_tokens"] == 200

    def test_review_passes_system_prompt(self) -> None:
        """review() passes the system parameter to messages.create when provided."""
        client, mock_api = self._make_client()
        mock_api.messages.create.return_value = _make_message()

        client.review(
            messages=[{"role": "user", "content": "Review."}],
            system="You are a code reviewer.",
        )

        call_kwargs = mock_api.messages.create.call_args
        assert call_kwargs.kwargs["system"] == "You are a code reviewer."

    def test_review_omits_system_when_none(self) -> None:
        """review() does not pass system key when system is None."""
        client, mock_api = self._make_client()
        mock_api.messages.create.return_value = _make_message()

        client.review(messages=[{"role": "user", "content": "Review."}])

        call_kwargs = mock_api.messages.create.call_args
        assert "system" not in call_kwargs.kwargs

    def test_review_forces_tool_choice(self) -> None:
        """review() forces tool_choice to submit_review."""
        client, mock_api = self._make_client()
        mock_api.messages.create.return_value = _make_message()

        client.review(messages=[{"role": "user", "content": "Review."}])

        call_kwargs = mock_api.messages.create.call_args
        assert call_kwargs.kwargs["tool_choice"] == {
            "type": "tool",
            "name": "submit_review",
        }

    def test_review_api_error_raises(self) -> None:
        """review() wraps anthropic.APIError into ClaudeReviewError."""
        client, mock_api = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {}
        mock_api.messages.create.side_effect = anthropic.APIStatusError(
            message="Internal Server Error",
            response=mock_response,
            body=None,
        )

        with pytest.raises(ClaudeReviewError, match="API error"):
            client.review(messages=[{"role": "user", "content": "Review."}])

    def test_review_connection_error_raises(self) -> None:
        """review() wraps anthropic.APIConnectionError into ClaudeReviewError."""
        client, mock_api = self._make_client()
        mock_api.messages.create.side_effect = anthropic.APIConnectionError(
            request=MagicMock(),
        )

        with pytest.raises(ClaudeReviewError, match="API connection error"):
            client.review(messages=[{"role": "user", "content": "Review."}])

    def test_review_invalid_tool_input_raises(self) -> None:
        """review() wraps pydantic.ValidationError into ClaudeReviewError."""
        client, mock_api = self._make_client()
        # Tool input with invalid ripeness value
        bad_input = _make_tool_input(ripeness="invalid_value")
        message = _make_message(content=[_make_tool_use_block(bad_input)])
        mock_api.messages.create.return_value = message

        with pytest.raises(ClaudeReviewError, match="Invalid tool input"):
            client.review(messages=[{"role": "user", "content": "Review."}])

    def test_review_no_tool_block_raises(self) -> None:
        """review() raises ClaudeReviewError when response has no tool_use block."""
        client, mock_api = self._make_client()
        message = _make_message(content=[_make_text_block()])
        mock_api.messages.create.return_value = message

        with pytest.raises(ClaudeReviewError, match="No tool_use block found"):
            client.review(messages=[{"role": "user", "content": "Review."}])


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


class TestAcceptance:
    """End-to-end-style acceptance tests with mocked API."""

    def _make_client(self) -> tuple[ClaudeClient, MagicMock]:
        """Create a ClaudeClient with a mocked Anthropic client."""
        client = ClaudeClient(api_key="sk-test", model="claude-sonnet-4-6")
        mock_api = MagicMock()
        client._client = mock_api  # type: ignore[assignment]
        return client, mock_api

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
        client, mock_api = self._make_client()
        message = _make_message(
            content=[_make_text_block(), _make_tool_use_block(tool_input)],
        )
        mock_api.messages.create.return_value = message

        result = client.review(messages=[{"role": "user", "content": "Review."}])

        assert result.ripeness.value == "ripe"
        assert len(result.findings) == 1
        assert result.findings[0].file == "src/main.py"
        assert result.findings[0].severity.value == "minor"

    def test_accept_malformed_response_raises_typed_error(self) -> None:
        """A malformed tool response raises ClaudeReviewError, not a generic exception."""
        client, mock_api = self._make_client()
        bad_input = {"ripeness": "invalid", "summary": "", "walkthrough": "", "findings": []}
        message = _make_message(content=[_make_tool_use_block(bad_input)])
        mock_api.messages.create.return_value = message

        with pytest.raises(ClaudeReviewError):
            client.review(messages=[{"role": "user", "content": "Review."}])

    def test_accept_usage_captured(self) -> None:
        """Token usage from the API response is captured in the ReviewResult."""
        client, mock_api = self._make_client()
        usage = _make_usage(
            input_tokens=1200,
            output_tokens=300,
            cache_read_input_tokens=800,
        )
        mock_api.messages.create.return_value = _make_message(usage=usage)

        result = client.review(messages=[{"role": "user", "content": "Review."}])

        assert result.usage["input_tokens"] == 1200
        assert result.usage["output_tokens"] == 300
        assert result.usage["cache_read_input_tokens"] == 800


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


class TestRegression:
    """Regression tests to guard against unintended changes."""

    def _make_client(self) -> tuple[ClaudeClient, MagicMock]:
        """Create a ClaudeClient with a mocked Anthropic client."""
        client = ClaudeClient(api_key="sk-test", model="claude-sonnet-4-6")
        mock_api = MagicMock()
        client._client = mock_api  # type: ignore[assignment]
        return client, mock_api

    def test_tool_schema_used_in_call(self) -> None:
        """review() passes the ReviewResult tool schema to the API call."""
        client, mock_api = self._make_client()
        mock_api.messages.create.return_value = _make_message()

        client.review(messages=[{"role": "user", "content": "Review."}])

        call_kwargs = mock_api.messages.create.call_args
        tools = call_kwargs.kwargs["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "submit_review"
        assert "input_schema" in tools[0]

    def test_review_result_fields_snapshot(self) -> None:
        """ReviewResult from a mocked review matches the pinned fixture snapshot."""
        client, mock_api = self._make_client()
        mock_api.messages.create.return_value = _make_message()

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

    def _make_client(self) -> tuple[ClaudeClient, MagicMock]:
        """Create a ClaudeClient with a mocked Anthropic client."""
        client = ClaudeClient(api_key="sk-test", model="claude-sonnet-4-6")
        mock_api = MagicMock()
        client._client = mock_api  # type: ignore[assignment]
        return client, mock_api

    def test_api_messages_create_params(self) -> None:
        """messages.create is called with expected parameters."""
        client, mock_api = self._make_client()
        mock_api.messages.create.return_value = _make_message()

        client.review(
            messages=[{"role": "user", "content": "Review."}],
            system="Be concise.",
        )

        call_kwargs = mock_api.messages.create.call_args.kwargs
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

    def test_api_system_param_accepts_blocks(self) -> None:
        """review() passes a list of content blocks as the system parameter."""
        client, mock_api = self._make_client()
        mock_api.messages.create.return_value = _make_message()

        blocks = [
            {"type": "text", "text": "You are a reviewer.", "cache_control": {"type": "ephemeral"}}
        ]
        client.review(
            messages=[{"role": "user", "content": "Review."}],
            system=blocks,
        )

        call_kwargs = mock_api.messages.create.call_args.kwargs
        assert call_kwargs["system"] == blocks


# ---------------------------------------------------------------------------
# Prompt caching tests
# ---------------------------------------------------------------------------


class TestPromptCaching:
    """Tests for prompt caching support in ClaudeClient.review()."""

    def _make_client(self) -> tuple[ClaudeClient, MagicMock]:
        """Create a ClaudeClient with a mocked Anthropic client."""
        client = ClaudeClient(api_key="sk-test", model="claude-sonnet-4-6")
        mock_api = MagicMock()
        client._client = mock_api  # type: ignore[assignment]
        return client, mock_api

    def test_review_passes_cache_blocks(self) -> None:
        """review() forwards cache blocks to messages.create as system."""
        client, mock_api = self._make_client()
        mock_api.messages.create.return_value = _make_message()

        blocks = [{"type": "text", "text": "prompt", "cache_control": {"type": "ephemeral"}}]
        client.review(
            messages=[{"role": "user", "content": "Review."}],
            system=blocks,
        )

        call_kwargs = mock_api.messages.create.call_args.kwargs
        assert call_kwargs["system"] is blocks

    def test_review_plain_string_still_works(self) -> None:
        """review() still works when system is a plain string."""
        client, mock_api = self._make_client()
        mock_api.messages.create.return_value = _make_message()

        client.review(
            messages=[{"role": "user", "content": "Review."}],
            system="You are a code reviewer.",
        )

        call_kwargs = mock_api.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "You are a code reviewer."

    def test_accept_cache_usage_extracted(self) -> None:
        """Cache usage fields are extracted when present in the response."""
        client, mock_api = self._make_client()
        usage = _make_usage(
            input_tokens=300,
            output_tokens=100,
            cache_creation_input_tokens=200,
            cache_read_input_tokens=150,
        )
        mock_api.messages.create.return_value = _make_message(usage=usage)

        blocks = [{"type": "text", "text": "prompt", "cache_control": {"type": "ephemeral"}}]
        result = client.review(
            messages=[{"role": "user", "content": "Review."}],
            system=blocks,
        )

        assert result.usage["cache_creation_input_tokens"] == 200
        assert result.usage["cache_read_input_tokens"] == 150

    def test_logs_cache_blocks_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        """Debug log message is emitted when using cache blocks."""
        client, mock_api = self._make_client()
        mock_api.messages.create.return_value = _make_message()

        blocks = [{"type": "text", "text": "prompt", "cache_control": {"type": "ephemeral"}}]
        import logging

        with caplog.at_level(logging.DEBUG, logger="lychee.claude"):
            client.review(
                messages=[{"role": "user", "content": "Review."}],
                system=blocks,
            )

        assert any("cache blocks" in r.message for r in caplog.records)

    def test_logs_plain_string_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        """Debug log message is emitted when using a plain string system prompt."""
        client, mock_api = self._make_client()
        mock_api.messages.create.return_value = _make_message()

        import logging

        with caplog.at_level(logging.DEBUG, logger="lychee.claude"):
            client.review(
                messages=[{"role": "user", "content": "Review."}],
                system="You are a reviewer.",
            )

        assert any("plain string" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Model override tests
# ---------------------------------------------------------------------------


class TestModelOverride:
    """Tests for the model_override parameter in ClaudeClient.review()."""

    def _make_client(self) -> tuple[ClaudeClient, MagicMock]:
        """Create a ClaudeClient with a mocked Anthropic client."""
        client = ClaudeClient(api_key="sk-test", model="claude-sonnet-4-6")
        mock_api = MagicMock()
        client._client = mock_api  # type: ignore[assignment]
        return client, mock_api

    def test_review_model_override(self) -> None:
        """model_override overrides self._model for the API call."""
        client, mock_api = self._make_client()
        mock_api.messages.create.return_value = _make_message()

        client.review(
            messages=[{"role": "user", "content": "Review."}],
            model_override="claude-opus-4-8",
        )

        call_kwargs = mock_api.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-opus-4-8"

    def test_review_model_override_none(self) -> None:
        """model_override=None uses self._model."""
        client, mock_api = self._make_client()
        mock_api.messages.create.return_value = _make_message()

        client.review(
            messages=[{"role": "user", "content": "Review."}],
            model_override=None,
        )

        call_kwargs = mock_api.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-6"

    def test_review_model_override_in_result(self) -> None:
        """Overridden model appears in ReviewResult.model."""
        client, mock_api = self._make_client()
        mock_api.messages.create.return_value = _make_message()

        result = client.review(
            messages=[{"role": "user", "content": "Review."}],
            model_override="claude-opus-4-8",
        )

        assert result.model == "claude-opus-4-8"


# ---------------------------------------------------------------------------
# Rate limiter integration tests (mocked API)
# ---------------------------------------------------------------------------


class TestRateLimiterIntegration:
    """Integration tests for ClaudeClient with rate limiter and retry config."""

    def _make_client_with_limiter(
        self,
        rate_limiter: TokenBucketLimiter | None = None,
        retry_config: RetryConfig | None = None,
    ) -> tuple[ClaudeClient, MagicMock]:
        """Create a ClaudeClient with optional rate limiter/retry and a mocked API."""
        client = ClaudeClient(
            api_key="sk-test",
            model="claude-sonnet-4-6",
            rate_limiter=rate_limiter,
            retry_config=retry_config,
        )
        mock_api = MagicMock()
        client._client = mock_api  # type: ignore[assignment]
        return client, mock_api

    @patch("lychee.rate_limiter.time.sleep")
    @patch("lychee.rate_limiter.time.monotonic", return_value=0.0)
    def test_claude_review_with_rate_limiter(
        self, mock_monotonic: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """acquire() is called before messages.create() when a rate limiter is set."""
        limiter = TokenBucketLimiter(capacity=5, refill_rate=1.0)
        client, mock_api = self._make_client_with_limiter(rate_limiter=limiter)
        mock_api.messages.create.return_value = _make_message()

        call_order: list[str] = []
        original_acquire = limiter.acquire

        def track_acquire(timeout: float = 30.0) -> None:
            call_order.append("acquire")
            original_acquire(timeout)

        limiter.acquire = track_acquire  # type: ignore[assignment]

        original_create = mock_api.messages.create

        def track_create(**kwargs: Any) -> Any:
            call_order.append("create")
            return original_create(**kwargs)

        mock_api.messages.create = track_create

        client.review(messages=[{"role": "user", "content": "Review."}])

        assert call_order == ["acquire", "create"]

    @patch("lychee.rate_limiter.time.sleep")
    def test_claude_review_retry_on_rate_limit(self, mock_sleep: MagicMock) -> None:
        """messages.create raises RateLimitError once then succeeds; retry occurs."""
        retry_config = RetryConfig(max_retries=3, base_delay=1.0, jitter=False)
        client, mock_api = self._make_client_with_limiter(retry_config=retry_config)

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        rate_err = anthropic.RateLimitError(
            message="Rate limited", response=mock_response, body=None
        )
        mock_api.messages.create.side_effect = [rate_err, _make_message()]

        result = client.review(messages=[{"role": "user", "content": "Review."}])

        assert result.ripeness.value == "ripe"
        assert mock_api.messages.create.call_count == 2

    @patch("lychee.rate_limiter.time.sleep")
    def test_claude_review_retry_on_server_error(self, mock_sleep: MagicMock) -> None:
        """messages.create raises InternalServerError once then succeeds."""
        retry_config = RetryConfig(max_retries=3, base_delay=1.0, jitter=False)
        client, mock_api = self._make_client_with_limiter(retry_config=retry_config)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {}
        server_err = anthropic.InternalServerError(
            message="Internal Server Error", response=mock_response, body=None
        )
        mock_api.messages.create.side_effect = [server_err, _make_message()]

        result = client.review(messages=[{"role": "user", "content": "Review."}])

        assert result.ripeness.value == "ripe"
        assert mock_api.messages.create.call_count == 2

    @patch("lychee.rate_limiter.time.sleep")
    def test_claude_review_no_retry_on_auth_error(self, mock_sleep: MagicMock) -> None:
        """AuthenticationError is not retried; raises ClaudeReviewError immediately."""
        retry_config = RetryConfig(max_retries=3, base_delay=1.0, jitter=False)
        client, mock_api = self._make_client_with_limiter(retry_config=retry_config)

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}
        auth_err = anthropic.AuthenticationError(
            message="Invalid API key", response=mock_response, body=None
        )
        mock_api.messages.create.side_effect = auth_err

        with pytest.raises(ClaudeReviewError, match="API error"):
            client.review(messages=[{"role": "user", "content": "Review."}])

        # No retries: only 1 call
        mock_api.messages.create.assert_called_once()

    @patch("lychee.rate_limiter.time.sleep")
    def test_claude_review_retry_exhausted(self, mock_sleep: MagicMock) -> None:
        """All retries exhausted; raises ClaudeReviewError."""
        retry_config = RetryConfig(max_retries=2, base_delay=1.0, jitter=False)
        client, mock_api = self._make_client_with_limiter(retry_config=retry_config)

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        rate_err = anthropic.RateLimitError(
            message="Rate limited", response=mock_response, body=None
        )
        mock_api.messages.create.side_effect = rate_err

        with pytest.raises(ClaudeReviewError, match="API error"):
            client.review(messages=[{"role": "user", "content": "Review."}])

        # 1 initial + 2 retries = 3 calls
        assert mock_api.messages.create.call_count == 3


# ---------------------------------------------------------------------------
# Rate limiter acceptance tests
# ---------------------------------------------------------------------------


class TestRateLimiterAcceptance:
    """Acceptance tests for rate limiting and retry behavior."""

    def _make_client_with_limiter(
        self,
        rate_limiter: TokenBucketLimiter | None = None,
        retry_config: RetryConfig | None = None,
    ) -> tuple[ClaudeClient, MagicMock]:
        """Create a ClaudeClient with optional rate limiter/retry and a mocked API."""
        client = ClaudeClient(
            api_key="sk-test",
            model="claude-sonnet-4-6",
            rate_limiter=rate_limiter,
            retry_config=retry_config,
        )
        mock_api = MagicMock()
        client._client = mock_api  # type: ignore[assignment]
        return client, mock_api

    @patch("lychee.rate_limiter.time.sleep")
    @patch("lychee.rate_limiter.time.monotonic", return_value=0.0)
    def test_accept_bursts_within_tier(
        self, mock_monotonic: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """A burst of 5 calls with a tier1 limiter all succeed without exhaustion."""
        from lychee.rate_limiter import default_rate_limiter

        limiter = default_rate_limiter("tier1")  # capacity=5
        client, mock_api = self._make_client_with_limiter(rate_limiter=limiter)
        mock_api.messages.create.return_value = _make_message()

        for _ in range(5):
            result = client.review(messages=[{"role": "user", "content": "Review."}])
            assert result.ripeness.value == "ripe"

        # All 5 calls succeeded without RateLimitExhaustedError
        assert mock_api.messages.create.call_count == 5

    @patch("lychee.rate_limiter.time.sleep")
    def test_accept_transient_errors_retried(self, mock_sleep: MagicMock) -> None:
        """Transient API errors are retried and the review completes successfully."""
        retry_config = RetryConfig(max_retries=3, base_delay=0.1, jitter=False)
        client, mock_api = self._make_client_with_limiter(retry_config=retry_config)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {}
        server_err = anthropic.InternalServerError(
            message="Internal Server Error", response=mock_response, body=None
        )
        # Fail twice, then succeed
        mock_api.messages.create.side_effect = [server_err, server_err, _make_message()]

        result = client.review(messages=[{"role": "user", "content": "Review."}])

        assert result.ripeness.value == "ripe"
        assert result.summary == "Looks good."

    @patch("lychee.rate_limiter.time.sleep")
    def test_accept_no_data_loss_on_retry(self, mock_sleep: MagicMock) -> None:
        """After retries, the returned ReviewResult is identical to the successful response."""
        retry_config = RetryConfig(max_retries=3, base_delay=0.1, jitter=False)
        client, mock_api = self._make_client_with_limiter(retry_config=retry_config)

        expected_tool_input = _make_tool_input(
            summary="Detailed review after retry.",
            findings=[
                {
                    "file": "src/app.py",
                    "line": 42,
                    "severity": "major",
                    "category": "correctness",
                    "message": "Off-by-one error in loop.",
                }
            ],
        )
        expected_message = _make_message(
            content=[_make_tool_use_block(expected_tool_input)],
            usage=_make_usage(input_tokens=800, output_tokens=400),
        )

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        rate_err = anthropic.RateLimitError(
            message="Rate limited", response=mock_response, body=None
        )
        mock_api.messages.create.side_effect = [rate_err, expected_message]

        result = client.review(messages=[{"role": "user", "content": "Review."}])

        assert result.summary == "Detailed review after retry."
        assert len(result.findings) == 1
        assert result.findings[0].file == "src/app.py"
        assert result.findings[0].line == 42
        assert result.usage["input_tokens"] == 800
        assert result.usage["output_tokens"] == 400


# ---------------------------------------------------------------------------
# Sanity: backward compatibility without limiter
# ---------------------------------------------------------------------------


class TestSanityRateLimiter:
    """Sanity tests verifying backward compatibility."""

    def test_claude_client_without_limiter_unchanged(self) -> None:
        """ClaudeClient without rate limiter/retry config behaves identically."""
        client = ClaudeClient(api_key="sk-test", model="claude-sonnet-4-6")
        mock_api = MagicMock()
        client._client = mock_api  # type: ignore[assignment]
        mock_api.messages.create.return_value = _make_message()

        result = client.review(messages=[{"role": "user", "content": "Review."}])

        assert result.ripeness.value == "ripe"
        assert result.summary == "Looks good."
        mock_api.messages.create.assert_called_once()


# ---------------------------------------------------------------------------
# API: retryable / non-retryable error classification
# ---------------------------------------------------------------------------


class TestAPIErrorClassification:
    """Tests verifying correct classification of API errors as retryable or not."""

    @patch("lychee.rate_limiter.time.sleep")
    def test_api_rate_limit_error_shape(self, mock_sleep: MagicMock) -> None:
        """RateLimitError (HTTP 429) is classified as retryable."""
        retry_config = RetryConfig(max_retries=1, base_delay=0.1, jitter=False)
        client = ClaudeClient(
            api_key="sk-test", model="claude-sonnet-4-6", retry_config=retry_config
        )
        mock_api = MagicMock()
        client._client = mock_api  # type: ignore[assignment]

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        rate_err = anthropic.RateLimitError(
            message="Rate limited", response=mock_response, body=None
        )
        mock_api.messages.create.side_effect = [rate_err, _make_message()]

        result = client.review(messages=[{"role": "user", "content": "Review."}])

        assert result.ripeness.value == "ripe"
        assert mock_api.messages.create.call_count == 2  # Retried once

    @patch("lychee.rate_limiter.time.sleep")
    def test_api_internal_server_error_shape(self, mock_sleep: MagicMock) -> None:
        """InternalServerError (HTTP 500/529) is classified as retryable."""
        retry_config = RetryConfig(max_retries=1, base_delay=0.1, jitter=False)
        client = ClaudeClient(
            api_key="sk-test", model="claude-sonnet-4-6", retry_config=retry_config
        )
        mock_api = MagicMock()
        client._client = mock_api  # type: ignore[assignment]

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {}
        server_err = anthropic.InternalServerError(
            message="Internal error", response=mock_response, body=None
        )
        mock_api.messages.create.side_effect = [server_err, _make_message()]

        result = client.review(messages=[{"role": "user", "content": "Review."}])

        assert result.ripeness.value == "ripe"
        assert mock_api.messages.create.call_count == 2  # Retried once

    @patch("lychee.rate_limiter.time.sleep")
    def test_api_auth_error_not_retryable(self, mock_sleep: MagicMock) -> None:
        """AuthenticationError (HTTP 401) is not retried."""
        retry_config = RetryConfig(max_retries=3, base_delay=0.1, jitter=False)
        client = ClaudeClient(
            api_key="sk-test", model="claude-sonnet-4-6", retry_config=retry_config
        )
        mock_api = MagicMock()
        client._client = mock_api  # type: ignore[assignment]

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}
        auth_err = anthropic.AuthenticationError(
            message="Invalid API key", response=mock_response, body=None
        )
        mock_api.messages.create.side_effect = auth_err

        with pytest.raises(ClaudeReviewError, match="API error"):
            client.review(messages=[{"role": "user", "content": "Review."}])

        # No retries
        mock_api.messages.create.assert_called_once()
