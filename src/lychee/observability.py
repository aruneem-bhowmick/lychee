"""Per-run observability: correlation IDs, structured logging, and run records.

Provides ContextVar-based correlation IDs that tag every log record in a
review run, a structured JSON logging formatter, and helpers to build and
emit an auditable run record capturing key metrics (repo, PR, model, tokens,
cost, ripeness, findings, duration).
"""

from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from lychee.models import Severity

# ---------------------------------------------------------------------------
# ContextVars — per-run state
# ---------------------------------------------------------------------------

_correlation_id: ContextVar[str] = ContextVar("_correlation_id", default="")
_review_strategy: ContextVar[str] = ContextVar("_review_strategy", default="single_pass")
_triage_verdict: ContextVar[str | None] = ContextVar("_triage_verdict", default=None)


def new_correlation_id() -> str:
    """Generate a new UUID4 correlation ID and store it in the ContextVar."""
    cid = uuid.uuid4().hex
    _correlation_id.set(cid)
    return cid


def get_correlation_id() -> str:
    """Return the current correlation ID, or empty string if unset."""
    return _correlation_id.get()


def set_review_strategy(strategy: str) -> None:
    """Set the review strategy for the current run."""
    _review_strategy.set(strategy)


def get_review_strategy() -> str:
    """Return the current review strategy."""
    return _review_strategy.get()


def set_triage_verdict(verdict: str | None) -> None:
    """Set the triage verdict for the current run."""
    _triage_verdict.set(verdict)


def get_triage_verdict() -> str | None:
    """Return the current triage verdict, or None if unset."""
    return _triage_verdict.get()


# ---------------------------------------------------------------------------
# Logging infrastructure
# ---------------------------------------------------------------------------


class CorrelationFilter(logging.Filter):
    """Inject ``correlation_id`` into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation_id attribute to the record and always return True."""
        record.correlation_id = get_correlation_id()
        return True


def setup_structured_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with JSON format including correlation_id.

    Replaces existing handlers on the root logger.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setLevel(level)
    fmt = (
        '{"time":"%(asctime)s","name":"%(name)s",'
        '"level":"%(levelname)s","correlation_id":"%(correlation_id)s",'
        '"message":"%(message)s"}'
    )
    handler.setFormatter(logging.Formatter(fmt))
    handler.addFilter(CorrelationFilter())
    root.addHandler(handler)


# ---------------------------------------------------------------------------
# Finding counts
# ---------------------------------------------------------------------------


def compute_finding_counts(findings: list[Any]) -> dict[str, int]:
    """Group findings by severity, filling missing severities with 0."""
    counts: dict[str, int] = {s.value: 0 for s in Severity}
    for f in findings:
        key = f.severity.value if hasattr(f.severity, "value") else str(f.severity)
        counts[key] = counts.get(key, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Run record
# ---------------------------------------------------------------------------


def build_run_record(
    *,
    repo: str,
    pr_number: int,
    head_sha: str,
    model: str,
    usage: dict[str, Any],
    cost_usd: float,
    ripeness: str,
    finding_counts: dict[str, int],
    duration_seconds: float,
    review_strategy: str,
    triage_verdict: str | None = None,
) -> dict[str, Any]:
    """Build a structured run record dict for auditing.

    All parameters are keyword-only. No PR content or secrets are included.
    """
    return {
        "event": "review_complete",
        "correlation_id": get_correlation_id(),
        "timestamp": datetime.now(UTC).isoformat(),
        "repo": repo,
        "pr_number": pr_number,
        "head_sha": head_sha,
        "model": model,
        "usage": usage,
        "cost_usd": cost_usd,
        "ripeness": ripeness,
        "finding_counts": finding_counts,
        "duration_seconds": round(duration_seconds, 3),
        "review_strategy": review_strategy,
        "triage_verdict": triage_verdict,
    }


def emit_run_record(record: dict[str, Any]) -> None:
    """Log a run record as a single JSON line."""
    logging.getLogger("lychee.run_record").info(json.dumps(record, default=str))
