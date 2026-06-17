"""Unit, system, regression, and smoke tests for lychee.rate_limiter.

Covers TokenBucketLimiter, RetryConfig, retry_with_backoff,
default_rate_limiter, and RateLimitExhaustedError.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from lychee.rate_limiter import (
    RateLimitExhaustedError,
    RetryConfig,
    TokenBucketLimiter,
    default_rate_limiter,
    retry_with_backoff,
)

# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


class TestSmoke:
    """Ensure the module imports cleanly."""

    def test_rate_limiter_module_imports(self) -> None:
        """TokenBucketLimiter, RetryConfig, and retry_with_backoff import successfully."""
        from lychee.rate_limiter import (
            RateLimitExhaustedError,
            RetryConfig,
            TokenBucketLimiter,
            retry_with_backoff,
        )

        assert callable(TokenBucketLimiter)
        assert callable(RetryConfig)
        assert callable(retry_with_backoff)
        assert issubclass(RateLimitExhaustedError, Exception)


# ---------------------------------------------------------------------------
# TokenBucketLimiter — unit tests
# ---------------------------------------------------------------------------


class TestTokenBucketAcquire:
    """Unit tests for TokenBucketLimiter.acquire()."""

    @patch("lychee.rate_limiter.time.sleep")
    @patch("lychee.rate_limiter.time.monotonic")
    def test_token_bucket_acquire_immediate(
        self, mock_monotonic: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """Bucket at capacity; acquire succeeds immediately without sleeping."""
        mock_monotonic.return_value = 0.0
        limiter = TokenBucketLimiter(capacity=5, refill_rate=1.0)

        limiter.acquire()

        mock_sleep.assert_not_called()

    @patch("lychee.rate_limiter.time.sleep")
    @patch("lychee.rate_limiter.time.monotonic")
    def test_token_bucket_acquire_depleted(
        self, mock_monotonic: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """Bucket empty; acquire blocks and then succeeds after refill."""
        # Sequence: init(0.0), acquire1 deadline(0.0), acquire1 now(0.0) -> success,
        # acquire2 deadline(0.0), acquire2 now(0.0) -> wait,
        # acquire2 now(1.0) -> success after refill
        mock_monotonic.side_effect = [0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        limiter = TokenBucketLimiter(capacity=1, refill_rate=1.0)

        limiter.acquire(timeout=30.0)  # Depletes the single token
        limiter.acquire(timeout=30.0)  # Must wait for refill

        mock_sleep.assert_called_once()

    @patch("lychee.rate_limiter.time.sleep")
    @patch("lychee.rate_limiter.time.monotonic")
    def test_token_bucket_acquire_timeout(
        self, mock_monotonic: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """Bucket empty with short timeout; raises RateLimitExhaustedError."""
        # init(0.0), acquire1 deadline(0.0), acquire1 now(0.0) -> success,
        # acquire2 deadline(0.0), acquire2 now(0.0) -> wait,
        # acquire2 now(0.1) -> timeout expired (deadline = 0.0 + 0.01 = 0.01)
        mock_monotonic.side_effect = [0.0, 0.0, 0.0, 0.0, 0.0, 0.1]
        limiter = TokenBucketLimiter(capacity=1, refill_rate=1.0)

        limiter.acquire(timeout=30.0)  # Depletes the single token

        with pytest.raises(RateLimitExhaustedError, match="Could not acquire token"):
            limiter.acquire(timeout=0.01)

    @patch("lychee.rate_limiter.time.sleep")
    @patch("lychee.rate_limiter.time.monotonic")
    def test_token_bucket_refill_caps_at_capacity(
        self, mock_monotonic: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """After a long idle period, tokens do not exceed capacity."""
        # init(0.0), acquire deadline(0.0), acquire now(100.0) -> refill capped at 5
        mock_monotonic.side_effect = [0.0, 0.0, 100.0]
        limiter = TokenBucketLimiter(capacity=5, refill_rate=1.0)

        limiter.acquire(timeout=30.0)
        mock_sleep.assert_not_called()

        # Verify internal state: tokens should be 4.0 (5 capped - 1 consumed)
        assert limiter._tokens == 4.0


# ---------------------------------------------------------------------------
# RetryConfig — unit tests
# ---------------------------------------------------------------------------


class TestRetryConfig:
    """Tests for RetryConfig defaults and custom values."""

    def test_retry_config_defaults(self) -> None:
        """Default values: max_retries=3, base_delay=1.0, max_delay=60.0, jitter=True."""
        config = RetryConfig()

        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.jitter is True

    def test_retry_config_custom(self) -> None:
        """Custom values are stored correctly."""
        config = RetryConfig(max_retries=5, base_delay=0.5, max_delay=30.0, jitter=False)

        assert config.max_retries == 5
        assert config.base_delay == 0.5
        assert config.max_delay == 30.0
        assert config.jitter is False


# ---------------------------------------------------------------------------
# retry_with_backoff — unit tests
# ---------------------------------------------------------------------------


class TestRetryWithBackoff:
    """Unit tests for the retry_with_backoff wrapper."""

    @patch("lychee.rate_limiter.time.sleep")
    def test_retry_with_backoff_no_error(self, mock_sleep: MagicMock) -> None:
        """fn succeeds on first try; no retries or sleeps occur."""
        fn = MagicMock(return_value="ok")
        config = RetryConfig(max_retries=3, jitter=False)
        wrapped = retry_with_backoff(fn, config, (ValueError,))

        result = wrapped()

        assert result == "ok"
        fn.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("lychee.rate_limiter.time.sleep")
    def test_retry_with_backoff_retries_on_retryable(self, mock_sleep: MagicMock) -> None:
        """fn fails with retryable exception twice, succeeds third; 3 calls total."""
        fn = MagicMock(side_effect=[ValueError("err"), ValueError("err"), "ok"])
        config = RetryConfig(max_retries=3, jitter=False)
        wrapped = retry_with_backoff(fn, config, (ValueError,))

        result = wrapped()

        assert result == "ok"
        assert fn.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("lychee.rate_limiter.time.sleep")
    def test_retry_with_backoff_exhausted(self, mock_sleep: MagicMock) -> None:
        """fn always fails; raises after max_retries."""
        fn = MagicMock(side_effect=ValueError("persistent error"))
        config = RetryConfig(max_retries=3, jitter=False)
        wrapped = retry_with_backoff(fn, config, (ValueError,))

        with pytest.raises(ValueError, match="persistent error"):
            wrapped()

        assert fn.call_count == 4  # 1 initial + 3 retries

    @patch("lychee.rate_limiter.time.sleep")
    def test_retry_with_backoff_non_retryable(self, mock_sleep: MagicMock) -> None:
        """fn fails with non-retryable exception; raises immediately without retry."""
        fn = MagicMock(side_effect=TypeError("non-retryable"))
        config = RetryConfig(max_retries=3, jitter=False)
        wrapped = retry_with_backoff(fn, config, (ValueError,))

        with pytest.raises(TypeError, match="non-retryable"):
            wrapped()

        fn.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("lychee.rate_limiter.time.sleep")
    def test_retry_with_backoff_respects_retry_after(self, mock_sleep: MagicMock) -> None:
        """RateLimitError with Retry-After header; delay matches header value."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"retry-after": "5.0"}
        rate_limit_exc = anthropic.RateLimitError(
            message="Rate limited",
            response=mock_response,
            body=None,
        )
        fn = MagicMock(side_effect=[rate_limit_exc, "ok"])
        config = RetryConfig(max_retries=3, jitter=False)
        wrapped = retry_with_backoff(fn, config, (anthropic.RateLimitError,))

        result = wrapped()

        assert result == "ok"
        # Should use the Retry-After header value (5.0) instead of computed delay
        mock_sleep.assert_called_once()
        actual_delay: float = mock_sleep.call_args[0][0]
        assert actual_delay == 5.0

    @patch("lychee.rate_limiter.time.sleep")
    def test_retry_with_backoff_jitter(self, mock_sleep: MagicMock) -> None:
        """With jitter=True, delays vary; with jitter=False, delays are deterministic."""
        fn_no_jitter = MagicMock(side_effect=[ValueError("e"), ValueError("e"), "ok"])
        config_no_jitter = RetryConfig(max_retries=3, base_delay=1.0, jitter=False)
        wrapped_no_jitter = retry_with_backoff(fn_no_jitter, config_no_jitter, (ValueError,))
        wrapped_no_jitter()

        delays_no_jitter = [call[0][0] for call in mock_sleep.call_args_list]
        assert delays_no_jitter == [1.0, 2.0]

        mock_sleep.reset_mock()

        fn_jitter = MagicMock(side_effect=[ValueError("e"), ValueError("e"), "ok"])
        config_jitter = RetryConfig(max_retries=3, base_delay=1.0, jitter=True)
        wrapped_jitter = retry_with_backoff(fn_jitter, config_jitter, (ValueError,))
        wrapped_jitter()

        delays_jitter = [call[0][0] for call in mock_sleep.call_args_list]
        # With jitter, delays should be modified by a [0.5, 1.5] multiplier
        assert len(delays_jitter) == 2
        assert 0.5 <= delays_jitter[0] <= 1.5  # base_delay * [0.5, 1.5]
        assert 1.0 <= delays_jitter[1] <= 3.0  # 2.0 * [0.5, 1.5]


# ---------------------------------------------------------------------------
# default_rate_limiter — unit tests
# ---------------------------------------------------------------------------


class TestDefaultRateLimiter:
    """Tests for the default_rate_limiter factory function."""

    def test_default_rate_limiter_tiers(self) -> None:
        """Each tier returns a TokenBucketLimiter with expected capacity and refill_rate."""
        expected: dict[str, tuple[int, float]] = {
            "tier1": (5, 1.0),
            "tier2": (10, 2.0),
            "tier3": (20, 5.0),
            "tier4": (50, 10.0),
        }
        for tier, (cap, rate) in expected.items():
            limiter = default_rate_limiter(tier)
            assert isinstance(limiter, TokenBucketLimiter)
            assert limiter.capacity == cap
            assert limiter.refill_rate == rate

    def test_default_rate_limiter_unknown_tier(self) -> None:
        """Unknown tier raises ValueError."""
        with pytest.raises(ValueError, match="Unknown tier"):
            default_rate_limiter("tier99")


# ---------------------------------------------------------------------------
# System tests
# ---------------------------------------------------------------------------


class TestSystem:
    """System-level tests for rate limiter concurrency."""

    def test_system_rate_limiter_concurrent(self) -> None:
        """Multiple threads acquire tokens from a shared limiter without starvation."""
        # Capacity of 10 with fast refill ensures all threads succeed quickly.
        limiter = TokenBucketLimiter(capacity=10, refill_rate=100.0)
        results: list[bool] = []
        lock = threading.Lock()

        def worker() -> None:
            limiter.acquire(timeout=5.0)
            with lock:
                results.append(True)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert len(results) == 10


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


class TestRegression:
    """Regression tests to pin expected behavior."""

    @patch("lychee.rate_limiter.time.sleep")
    def test_retry_delay_sequence(self, mock_sleep: MagicMock) -> None:
        """For max_retries=3, base_delay=1.0, jitter=False: delays are [1.0, 2.0, 4.0]."""
        fn = MagicMock(side_effect=ValueError("always fails"))
        config = RetryConfig(max_retries=3, base_delay=1.0, jitter=False)
        wrapped = retry_with_backoff(fn, config, (ValueError,))

        with pytest.raises(ValueError):
            wrapped()

        delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert delays == [1.0, 2.0, 4.0]


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


class TestSanity:
    """Basic construction sanity checks."""

    def test_token_bucket_limiter_construction(self) -> None:
        """TokenBucketLimiter constructs with given parameters."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=2.0)
        assert limiter.capacity == 10
        assert limiter.refill_rate == 2.0

    def test_retry_config_construction(self) -> None:
        """RetryConfig constructs without raising."""
        config = RetryConfig(max_retries=5, base_delay=0.1)
        assert config.max_retries == 5
        assert config.base_delay == 0.1
