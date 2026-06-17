"""Tests for the cost accounting module (lychee.cost).

Covers unit tests for cost computation, budget checking, and cost-line
formatting; smoke tests for importability; sanity tests for determinism;
regression snapshot tests for pinned values; and acceptance tests for
spec-mandated cost accuracy and budget abort behaviour.

Framework: pytest.  Coverage target: >= 90% on src/lychee/cost.py.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from lychee.cost import (
    MODEL_PRICING,
    BudgetExceededError,
    check_budget,
    compute_cost,
    compute_total_cost,
    format_cost_line,
)

# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_cost_module_imports() -> None:
    """All public names import cleanly from lychee.cost."""
    from lychee.cost import (
        BudgetExceededError,
        check_budget,
        compute_cost,
        compute_total_cost,
        format_cost_line,
    )

    assert callable(compute_cost)
    assert callable(compute_total_cost)
    assert callable(format_cost_line)
    assert callable(check_budget)
    assert issubclass(BudgetExceededError, Exception)


# ---------------------------------------------------------------------------
# Unit tests — compute_cost
# ---------------------------------------------------------------------------


class TestComputeCost:
    """Unit tests for compute_cost()."""

    def test_compute_cost_sonnet(self) -> None:
        """Sonnet with 1000 input, 500 output yields the expected cost."""
        usage: dict[str, Any] = {"input_tokens": 1000, "output_tokens": 500}
        cost = compute_cost(usage, "claude-sonnet-4-6")
        # (1000/1M)*3.0 + (500/1M)*15.0 = 0.003 + 0.0075 = 0.0105
        assert cost == pytest.approx(0.0105)

    def test_compute_cost_opus(self) -> None:
        """Opus pricing is applied correctly."""
        usage: dict[str, Any] = {"input_tokens": 1000, "output_tokens": 500}
        cost = compute_cost(usage, "claude-opus-4-8")
        # (1000/1M)*5.0 + (500/1M)*25.0 = 0.005 + 0.0125 = 0.0175
        assert cost == pytest.approx(0.0175)

    def test_compute_cost_haiku(self) -> None:
        """Haiku pricing is applied correctly."""
        usage: dict[str, Any] = {"input_tokens": 1000, "output_tokens": 500}
        cost = compute_cost(usage, "claude-haiku-4-5-20251001")
        # (1000/1M)*1.0 + (500/1M)*5.0 = 0.001 + 0.0025 = 0.0035
        assert cost == pytest.approx(0.0035)

    def test_compute_cost_with_cache(self) -> None:
        """cache_read_input_tokens are priced at the discounted cached rate."""
        usage: dict[str, Any] = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_read_input_tokens": 800,
        }
        cost = compute_cost(usage, "claude-sonnet-4-6")
        # regular_input = 1000 - 800 = 200
        # (200/1M)*3.0 + (800/1M)*0.30 + (500/1M)*15.0
        # = 0.0006 + 0.00024 + 0.0075 = 0.00834
        assert cost == pytest.approx(0.00834)

    def test_compute_cost_with_cache_creation(self) -> None:
        """cache_creation_input_tokens are charged at the regular input rate.

        The API includes cache_creation tokens in input_tokens, so they are
        already accounted for at the regular rate. No special handling needed.
        """
        usage: dict[str, Any] = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_creation_input_tokens": 300,
        }
        cost = compute_cost(usage, "claude-sonnet-4-6")
        # No cache_read, so all 1000 input tokens at regular rate
        # (1000/1M)*3.0 + (500/1M)*15.0 = 0.003 + 0.0075 = 0.0105
        assert cost == pytest.approx(0.0105)

    def test_compute_cost_unknown_model(self, caplog: pytest.LogCaptureFixture) -> None:
        """Unknown model falls back to Sonnet pricing with a warning."""
        usage: dict[str, Any] = {"input_tokens": 1000, "output_tokens": 500}
        with caplog.at_level(logging.WARNING, logger="lychee.cost"):
            cost = compute_cost(usage, "unknown-model-xyz")

        # Should produce the same cost as Sonnet
        assert cost == pytest.approx(0.0105)
        assert "Unknown model" in caplog.text
        assert "unknown-model-xyz" in caplog.text

    def test_compute_cost_zero_tokens(self) -> None:
        """Zero input and output tokens yields zero cost."""
        usage: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0}
        cost = compute_cost(usage, "claude-sonnet-4-6")
        assert cost == 0.0

    def test_compute_cost_missing_keys(self) -> None:
        """Missing usage keys default to zero without error."""
        usage: dict[str, Any] = {}
        cost = compute_cost(usage, "claude-sonnet-4-6")
        assert cost == 0.0


# ---------------------------------------------------------------------------
# Unit tests — compute_total_cost
# ---------------------------------------------------------------------------


class TestComputeTotalCost:
    """Unit tests for compute_total_cost()."""

    def test_compute_total_cost(self) -> None:
        """Sum across multiple (usage, model) pairs."""
        usages: list[tuple[dict[str, Any], str]] = [
            ({"input_tokens": 1000, "output_tokens": 500}, "claude-sonnet-4-6"),
            ({"input_tokens": 2000, "output_tokens": 1000}, "claude-sonnet-4-6"),
        ]
        total = compute_total_cost(usages)
        # Call 1: 0.0105, Call 2: 0.021 → 0.0315
        assert total == pytest.approx(0.0315)

    def test_compute_total_cost_mixed_models(self) -> None:
        """Total cost across different models sums correctly."""
        usages: list[tuple[dict[str, Any], str]] = [
            ({"input_tokens": 1000, "output_tokens": 500}, "claude-sonnet-4-6"),
            ({"input_tokens": 1000, "output_tokens": 500}, "claude-haiku-4-5-20251001"),
        ]
        total = compute_total_cost(usages)
        # Sonnet: 0.0105, Haiku: 0.0035 → 0.014
        assert total == pytest.approx(0.014)

    def test_compute_total_cost_empty(self) -> None:
        """Empty list yields zero cost."""
        assert compute_total_cost([]) == 0.0


# ---------------------------------------------------------------------------
# Unit tests — format_cost_line
# ---------------------------------------------------------------------------


class TestFormatCostLine:
    """Unit tests for format_cost_line()."""

    def test_format_cost_line_basic(self) -> None:
        """Output matches the expected markdown format."""
        usage: dict[str, Any] = {"input_tokens": 5432, "output_tokens": 1234}
        line = format_cost_line(0.0123, usage)
        assert line == "**Cost:** $0.0123 | **Tokens:** 5,432 input, 1,234 output"

    def test_format_cost_line_with_cache(self) -> None:
        """Cached token count is included when cache_read_input_tokens > 0."""
        usage: dict[str, Any] = {
            "input_tokens": 5432,
            "output_tokens": 1234,
            "cache_read_input_tokens": 4000,
        }
        line = format_cost_line(0.0089, usage)
        assert line == "**Cost:** $0.0089 | **Tokens:** 5,432 input, 1,234 output, 4,000 cached"

    def test_format_cost_line_no_cache(self) -> None:
        """Cached segment is omitted when cache_read_input_tokens is 0."""
        usage: dict[str, Any] = {
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_read_input_tokens": 0,
        }
        line = format_cost_line(0.0060, usage)
        assert "cached" not in line

    def test_format_cost_line_absent_cache_key(self) -> None:
        """Cached segment is omitted when cache_read_input_tokens key is absent."""
        usage: dict[str, Any] = {"input_tokens": 1000, "output_tokens": 200}
        line = format_cost_line(0.0060, usage)
        assert "cached" not in line

    def test_format_cost_line_large_numbers(self) -> None:
        """Token counts use comma-separated thousands formatting."""
        usage: dict[str, Any] = {"input_tokens": 1_234_567, "output_tokens": 89_012}
        line = format_cost_line(5.1234, usage)
        assert "1,234,567 input" in line
        assert "89,012 output" in line


# ---------------------------------------------------------------------------
# Unit tests — check_budget
# ---------------------------------------------------------------------------


class TestCheckBudget:
    """Unit tests for check_budget()."""

    def test_check_budget_no_cap(self) -> None:
        """cap=None produces no exception regardless of spend."""
        check_budget(999.99, None)  # should not raise

    def test_check_budget_within_cap(self) -> None:
        """Spending below cap produces no exception."""
        check_budget(0.05, 1.0)  # should not raise

    def test_check_budget_exceeded(self) -> None:
        """Spending above cap raises BudgetExceededError with correct amounts."""
        with pytest.raises(BudgetExceededError) as exc_info:
            check_budget(1.50, 1.00)
        assert exc_info.value.spent_usd == pytest.approx(1.50)
        assert exc_info.value.cap_usd == pytest.approx(1.00)

    def test_check_budget_exact(self) -> None:
        """Spending exactly at cap does not raise (only strictly exceeding triggers)."""
        check_budget(1.00, 1.00)  # should not raise

    def test_budget_exceeded_error_message(self) -> None:
        """BudgetExceededError message includes dollar amounts."""
        err = BudgetExceededError(0.1234, 0.1000)
        assert "$0.1234" in str(err)
        assert "$0.1000" in str(err)
        assert "exceeded" in str(err).lower()


# ---------------------------------------------------------------------------
# Unit tests — BudgetExceededError
# ---------------------------------------------------------------------------


class TestBudgetExceededError:
    """Tests for the BudgetExceededError exception class."""

    def test_attributes(self) -> None:
        """spent_usd and cap_usd are accessible on the exception instance."""
        err = BudgetExceededError(0.5, 0.3)
        assert err.spent_usd == 0.5
        assert err.cap_usd == 0.3

    def test_is_exception(self) -> None:
        """BudgetExceededError is a subclass of Exception."""
        assert issubclass(BudgetExceededError, Exception)


# ---------------------------------------------------------------------------
# Unit tests — budget_cap_usd config validation
# ---------------------------------------------------------------------------


def test_budget_cap_config_validation() -> None:
    """budget_cap_usd <= 0 is rejected by config validation."""
    import pydantic

    from lychee.config import ReviewConfig

    with pytest.raises(pydantic.ValidationError):
        ReviewConfig(budget_cap_usd=-1.0)  # type: ignore[call-arg]

    with pytest.raises(pydantic.ValidationError):
        ReviewConfig(budget_cap_usd=0.0)  # type: ignore[call-arg]


def test_budget_cap_config_positive_accepted() -> None:
    """Positive budget_cap_usd values are accepted."""
    from lychee.config import ReviewConfig

    config = ReviewConfig(budget_cap_usd=0.50)  # type: ignore[call-arg]
    assert config.budget_cap_usd == 0.50


def test_budget_cap_config_none_accepted() -> None:
    """None budget_cap_usd (default) is accepted."""
    from lychee.config import ReviewConfig

    config = ReviewConfig()
    assert config.budget_cap_usd is None


# ---------------------------------------------------------------------------
# Unit tests — MODEL_PRICING
# ---------------------------------------------------------------------------


def test_model_pricing_keys() -> None:
    """MODEL_PRICING contains entries for Sonnet, Opus, and Haiku."""
    assert "claude-sonnet-4-6" in MODEL_PRICING
    assert "claude-opus-4-8" in MODEL_PRICING
    assert "claude-haiku-4-5-20251001" in MODEL_PRICING


def test_model_pricing_values_structure() -> None:
    """Each MODEL_PRICING entry is a 3-tuple of positive floats."""
    for model, rates in MODEL_PRICING.items():
        assert len(rates) == 3, f"{model} rates should be a 3-tuple"
        for rate in rates:
            assert isinstance(rate, float), f"{model} rate {rate} is not a float"
            assert rate > 0, f"{model} rate {rate} is not positive"


def test_cached_rate_cheaper_than_input() -> None:
    """Cached input rate is cheaper than regular input rate for all models."""
    for model, (input_rate, _, cached_rate) in MODEL_PRICING.items():
        assert (
            cached_rate < input_rate
        ), f"{model}: cached rate {cached_rate} should be < input rate {input_rate}"


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_reported_cost_matches_usage() -> None:
    """Compute cost from a known usage dict; verify it matches expected dollar amount."""
    usage: dict[str, Any] = {
        "input_tokens": 10_000,
        "output_tokens": 2_000,
        "cache_read_input_tokens": 5_000,
    }
    cost = compute_cost(usage, "claude-sonnet-4-6")
    # regular_input = 10000 - 5000 = 5000
    # (5000/1M)*3.0 + (5000/1M)*0.30 + (2000/1M)*15.0
    # = 0.015 + 0.0015 + 0.030 = 0.0465
    assert cost == pytest.approx(0.0465)


def test_accept_cap_aborts_cleanly() -> None:
    """A low budget cap triggers BudgetExceededError with a clear message."""
    with pytest.raises(BudgetExceededError, match="Budget exceeded"):
        check_budget(0.05, 0.01)


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_cost_deterministic() -> None:
    """compute_cost produces identical results on repeated calls."""
    usage: dict[str, Any] = {"input_tokens": 5000, "output_tokens": 1000}
    c1 = compute_cost(usage, "claude-sonnet-4-6")
    c2 = compute_cost(usage, "claude-sonnet-4-6")
    assert c1 == c2


# ---------------------------------------------------------------------------
# Regression (snapshot) tests
# ---------------------------------------------------------------------------


def test_cost_computation_snapshot() -> None:
    """For a fixed usage dict and model, cost is pinned to a specific value."""
    usage: dict[str, Any] = {
        "input_tokens": 8000,
        "output_tokens": 3000,
        "cache_read_input_tokens": 2000,
    }
    cost = compute_cost(usage, "claude-sonnet-4-6")
    # regular_input = 8000 - 2000 = 6000
    # (6000/1M)*3.0 + (2000/1M)*0.30 + (3000/1M)*15.0
    # = 0.018 + 0.0006 + 0.045 = 0.0636
    assert cost == pytest.approx(0.0636, abs=1e-6)


def test_cost_line_format_snapshot() -> None:
    """For a fixed cost/usage, the formatted line matches a pinned string."""
    usage: dict[str, Any] = {
        "input_tokens": 8000,
        "output_tokens": 3000,
        "cache_read_input_tokens": 2000,
    }
    line = format_cost_line(0.0636, usage)
    expected = "**Cost:** $0.0636 | **Tokens:** 8,000 input, 3,000 output, 2,000 cached"
    assert line == expected
