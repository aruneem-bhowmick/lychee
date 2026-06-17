"""Token-bucket rate limiter and exponential-backoff retry logic for API calls."""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

import anthropic

_logger = logging.getLogger(__name__)

T = TypeVar("T")


class RateLimitExhaustedError(Exception):
    """Raised when the rate limiter cannot acquire a token within the deadline."""


class TokenBucketLimiter:
    """Thread-safe token-bucket rate limiter.

    Configured with a capacity (max burst) and a refill rate (tokens per second).
    Callers call ``acquire()`` before making an API call; it blocks until a token
    is available or raises ``RateLimitExhaustedError`` if the deadline expires.
    """

    def __init__(self, capacity: int, refill_rate: float) -> None:
        """Initialise with bucket capacity and refill rate (tokens/second)."""
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._tokens: float = float(capacity)
        self._last_refill: float = time.monotonic()
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        """Return the bucket capacity."""
        return self._capacity

    @property
    def refill_rate(self) -> float:
        """Return the refill rate in tokens per second."""
        return self._refill_rate

    def acquire(self, timeout: float = 30.0) -> None:
        """Block until a token is available or *timeout* seconds expire.

        Raises ``RateLimitExhaustedError`` if no token becomes available within
        the given timeout.
        """
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(
                    self._capacity,
                    self._tokens + elapsed * self._refill_rate,
                )
                self._last_refill = now

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    _logger.debug("Token acquired (remaining=%.1f)", self._tokens)
                    return

                wait_time = (1.0 - self._tokens) / self._refill_rate
                remaining = deadline - now

                if remaining <= 0:
                    raise RateLimitExhaustedError(
                        f"Could not acquire token within {timeout:.1f}s timeout"
                    )

                sleep_time = min(wait_time, remaining)
                _logger.debug(
                    "No token available (tokens=%.2f), waiting %.2fs",
                    self._tokens,
                    sleep_time,
                )

            # Sleep outside the lock so other threads can acquire tokens.
            time.sleep(sleep_time)


class RetryConfig:
    """Configuration for exponential backoff retries."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
    ) -> None:
        """Initialise retry configuration.

        Args:
            max_retries: Maximum number of retry attempts after the initial call.
            base_delay: Base delay in seconds for exponential backoff.
            max_delay: Maximum delay cap in seconds between retries.
            jitter: Whether to apply random jitter to computed delays.
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter


def _extract_retry_after(exc: anthropic.RateLimitError) -> float | None:
    """Extract the ``Retry-After`` header value from a rate-limit error response."""
    try:
        retry_after = exc.response.headers.get("retry-after")
        if retry_after is not None:
            return float(retry_after)
    except (AttributeError, ValueError, TypeError):
        pass
    return None


def retry_with_backoff(
    fn: Callable[..., T],
    retry_config: RetryConfig,
    retryable_exceptions: tuple[type[Exception], ...],
) -> Callable[..., T]:
    """Wrap *fn* with exponential-backoff retry logic.

    Retries on exceptions listed in *retryable_exceptions* up to
    ``retry_config.max_retries`` times. Respects ``Retry-After`` headers
    from ``anthropic.RateLimitError`` when available. Re-raises the last
    exception if all retries are exhausted.
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        for attempt in range(retry_config.max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except retryable_exceptions as exc:
                if attempt == retry_config.max_retries:
                    _logger.warning(
                        "All %d retries exhausted for %s; raising %s",
                        retry_config.max_retries,
                        getattr(fn, "__name__", "unknown"),
                        type(exc).__name__,
                    )
                    raise

                delay = min(
                    retry_config.base_delay * (2**attempt),
                    retry_config.max_delay,
                )

                if isinstance(exc, anthropic.RateLimitError):
                    header_delay = _extract_retry_after(exc)
                    if header_delay is not None:
                        delay = header_delay

                if retry_config.jitter:
                    delay *= random.uniform(0.5, 1.5)

                _logger.warning(
                    "Retry %d/%d for %s after %s (delay=%.2fs)",
                    attempt + 1,
                    retry_config.max_retries,
                    getattr(fn, "__name__", "unknown"),
                    type(exc).__name__,
                    delay,
                )
                time.sleep(delay)

        # Unreachable: the loop always returns or raises.
        raise AssertionError("retry loop exited unexpectedly")  # pragma: no cover

    return wrapper


# ---------------------------------------------------------------------------
# Tier defaults
# ---------------------------------------------------------------------------

_TIER_CONFIGS: dict[str, tuple[int, float]] = {
    "tier1": (5, 1.0),
    "tier2": (10, 2.0),
    "tier3": (20, 5.0),
    "tier4": (50, 10.0),
}


def default_rate_limiter(tier: str = "tier1") -> TokenBucketLimiter:
    """Create a ``TokenBucketLimiter`` with sensible defaults for the given API tier.

    Supported tiers: ``tier1`` (capacity=5, 1 tok/s), ``tier2`` (10, 2),
    ``tier3`` (20, 5), ``tier4`` (50, 10).

    Raises ``ValueError`` for unrecognised tier names.
    """
    if tier not in _TIER_CONFIGS:
        raise ValueError(f"Unknown tier '{tier}'; supported: {sorted(_TIER_CONFIGS)}")
    capacity, refill_rate = _TIER_CONFIGS[tier]
    return TokenBucketLimiter(capacity=capacity, refill_rate=refill_rate)
