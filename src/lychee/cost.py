"""Cost accounting, budget enforcement, and cost-line formatting.

Provides per-run token cost computation from Anthropic API usage dicts,
an optional budget cap that raises ``BudgetExceededError`` when exceeded,
and a formatter for the cost footer line rendered in PR comments.

All cost computation is pure arithmetic with no I/O.
"""

from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)


class BudgetExceededError(Exception):
    """Raised when a review run exceeds the configured budget cap."""

    def __init__(self, spent_usd: float, cap_usd: float) -> None:
        self.spent_usd = spent_usd
        self.cap_usd = cap_usd
        super().__init__(f"Budget exceeded: ${spent_usd:.4f} spent, cap is ${cap_usd:.4f}")


# Model pricing: (input_cost_per_1m, output_cost_per_1m, cached_input_cost_per_1m)
MODEL_PRICING: dict[str, tuple[float, float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0, 0.30),
    "claude-opus-4-8": (5.0, 25.0, 0.50),
    "claude-haiku-4-5-20251001": (1.0, 5.0, 0.10),
}

_DEFAULT_MODEL: str = "claude-sonnet-4-6"


def compute_cost(
    usage: dict[str, Any],
    model: str,
) -> float:
    """Compute the dollar cost for a single API call given usage and model.

    Accounts for:

    - ``input_tokens`` at the model's input rate
    - ``output_tokens`` at the model's output rate
    - ``cache_read_input_tokens`` at the cached input rate (~90 % cheaper)
    - ``cache_creation_input_tokens`` at the regular input rate

    Cached-read tokens are subtracted from ``input_tokens`` so they are not
    double-counted at the regular rate.

    Unknown models fall back to Sonnet pricing with a logged warning.

    Returns:
        Cost in USD as a float.
    """
    if model in MODEL_PRICING:
        input_rate, output_rate, cached_rate = MODEL_PRICING[model]
    else:
        _logger.warning(
            "Unknown model %r — falling back to default (%s) pricing",
            model,
            _DEFAULT_MODEL,
        )
        input_rate, output_rate, cached_rate = MODEL_PRICING[_DEFAULT_MODEL]

    input_tokens: int = usage.get("input_tokens", 0)
    output_tokens: int = usage.get("output_tokens", 0)
    cache_read: int = usage.get("cache_read_input_tokens", 0)
    # cache_creation_input_tokens are charged at the regular input rate,
    # and they are already included in input_tokens by the API.
    # We only need to re-price cache_read tokens at the discounted rate.

    regular_input = input_tokens - cache_read
    cost = (
        (regular_input / 1_000_000) * input_rate
        + (cache_read / 1_000_000) * cached_rate
        + (output_tokens / 1_000_000) * output_rate
    )
    return cost


def compute_total_cost(
    usages: list[tuple[dict[str, Any], str]],
) -> float:
    """Compute total cost across multiple API calls.

    Each element is ``(usage_dict, model_id)``.

    Returns:
        Sum of per-call costs in USD.
    """
    return sum(compute_cost(usage, model) for usage, model in usages)


def format_cost_line(cost_usd: float, usage: dict[str, Any]) -> str:
    """Format the cost footer line for the rendered comment.

    Format::

        **Cost:** $X.XXXX | **Tokens:** N input, M output[, K cached]

    The cached segment is omitted when ``cache_read_input_tokens`` is absent
    or zero.
    """
    input_tokens: int = usage.get("input_tokens", 0)
    output_tokens: int = usage.get("output_tokens", 0)
    cache_read: int = usage.get("cache_read_input_tokens", 0)

    parts = [
        f"**Cost:** ${cost_usd:.4f}",
        f"**Tokens:** {input_tokens:,} input, {output_tokens:,} output",
    ]

    if cache_read:
        parts[1] += f", {cache_read:,} cached"

    return " | ".join(parts)


def check_budget(
    spent_usd: float,
    cap_usd: float | None,
) -> None:
    """Raise ``BudgetExceededError`` if *spent_usd* exceeds *cap_usd*.

    No-op when *cap_usd* is ``None`` (no budget cap configured).
    Spending exactly at the cap is allowed; only strictly exceeding it
    triggers the error.
    """
    if cap_usd is None:
        return
    if spent_usd > cap_usd:
        raise BudgetExceededError(spent_usd, cap_usd)
