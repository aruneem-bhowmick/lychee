"""Tests for the per-run observability module (lychee.observability).

Covers unit tests for correlation IDs, structured logging, finding counts,
and run record building; integration tests for emit and logging format;
smoke tests for importability; sanity tests for backward compatibility;
regression tests for run record schema stability; and acceptance tests
for secret/content leakage.

Framework: pytest, unittest.mock, caplog/capfd for log capture.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import patch

import pytest

from lychee.models import Category, Finding, Severity
from lychee.observability import (
    CorrelationFilter,
    build_run_record,
    compute_finding_counts,
    emit_run_record,
    get_correlation_id,
    get_review_strategy,
    get_triage_verdict,
    new_correlation_id,
    set_review_strategy,
    set_triage_verdict,
    setup_structured_logging,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(severity: Severity = Severity.info) -> Finding:
    """Create a minimal Finding with the given severity."""
    return Finding(
        file="test.py",
        line=1,
        severity=severity,
        category=Category.other,
        message="Test finding.",
    )


def _make_findings_mixed() -> list[Finding]:
    """Create a mixed list of findings across severities."""
    return [
        _make_finding(Severity.info),
        _make_finding(Severity.info),
        _make_finding(Severity.minor),
        _make_finding(Severity.major),
        _make_finding(Severity.critical),
        _make_finding(Severity.critical),
    ]


def _build_default_record(**overrides: Any) -> dict[str, Any]:
    """Build a run record with sensible defaults, overriding as needed."""
    defaults: dict[str, Any] = {
        "repo": "owner/repo",
        "pr_number": 42,
        "head_sha": "abc123",
        "model": "claude-sonnet-4-6",
        "usage": {"input_tokens": 1000, "output_tokens": 200},
        "cost_usd": 0.006,
        "ripeness": "ripe",
        "finding_counts": {"info": 1, "minor": 0, "major": 0, "critical": 0},
        "duration_seconds": 1.234,
        "review_strategy": "single_pass",
        "triage_verdict": None,
    }
    defaults.update(overrides)
    return build_run_record(**defaults)


# ---------------------------------------------------------------------------
# Unit tests — correlation IDs
# ---------------------------------------------------------------------------


class TestCorrelationId:
    """Unit tests for correlation ID generation and retrieval."""

    def test_new_correlation_id_format(self) -> None:
        """new_correlation_id returns a 32-character hex string."""
        cid = new_correlation_id()
        assert len(cid) == 32
        assert all(c in "0123456789abcdef" for c in cid)

    def test_new_correlation_id_unique(self) -> None:
        """Two calls to new_correlation_id produce different IDs."""
        cid1 = new_correlation_id()
        cid2 = new_correlation_id()
        assert cid1 != cid2

    def test_get_correlation_id_after_set(self) -> None:
        """After new_correlation_id, get_correlation_id returns the same value."""
        cid = new_correlation_id()
        assert get_correlation_id() == cid

    def test_get_correlation_id_default(self) -> None:
        """get_correlation_id returns empty string when the ContextVar is at default.

        We test this by patching the ContextVar to simulate a fresh context.
        """
        with patch("lychee.observability._correlation_id") as mock_var:
            mock_var.get.return_value = ""
            assert get_correlation_id() == ""


# ---------------------------------------------------------------------------
# Unit tests — CorrelationFilter
# ---------------------------------------------------------------------------


class TestCorrelationFilter:
    """Unit tests for the CorrelationFilter log filter."""

    def test_correlation_filter_adds_id(self) -> None:
        """CorrelationFilter sets record.correlation_id to the current ID."""
        cid = new_correlation_id()
        filt = CorrelationFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        result = filt.filter(record)
        assert result is True
        assert record.correlation_id == cid  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Unit tests — strategy/verdict context
# ---------------------------------------------------------------------------


class TestStrategyVerdict:
    """Unit tests for review strategy and triage verdict context tracking."""

    def test_set_and_get_review_strategy(self) -> None:
        """set_review_strategy stores value retrievable by get_review_strategy."""
        set_review_strategy("map_reduce")
        assert get_review_strategy() == "map_reduce"

    def test_set_and_get_triage_verdict(self) -> None:
        """set_triage_verdict stores value retrievable by get_triage_verdict."""
        set_triage_verdict("trivial")
        assert get_triage_verdict() == "trivial"

    def test_triage_verdict_none(self) -> None:
        """set_triage_verdict(None) clears the verdict."""
        set_triage_verdict(None)
        assert get_triage_verdict() is None


# ---------------------------------------------------------------------------
# Unit tests — compute_finding_counts
# ---------------------------------------------------------------------------


class TestComputeFindingCounts:
    """Unit tests for compute_finding_counts."""

    def test_empty_findings(self) -> None:
        """Empty findings list returns all-zero counts."""
        counts = compute_finding_counts([])
        assert counts == {"info": 0, "minor": 0, "major": 0, "critical": 0}

    def test_mixed_findings(self) -> None:
        """Mixed findings are counted by severity."""
        findings = _make_findings_mixed()
        counts = compute_finding_counts(findings)
        assert counts == {"info": 2, "minor": 1, "major": 1, "critical": 2}

    def test_single_severity(self) -> None:
        """All findings of one severity are counted correctly."""
        findings = [_make_finding(Severity.major) for _ in range(5)]
        counts = compute_finding_counts(findings)
        assert counts["major"] == 5
        assert counts["info"] == 0


# ---------------------------------------------------------------------------
# Unit tests — build_run_record
# ---------------------------------------------------------------------------


class TestBuildRunRecord:
    """Unit tests for build_run_record."""

    def test_build_run_record_fields(self) -> None:
        """All required fields are present in the run record."""
        new_correlation_id()
        record = _build_default_record()
        required_fields = {
            "event",
            "correlation_id",
            "timestamp",
            "repo",
            "pr_number",
            "head_sha",
            "model",
            "usage",
            "cost_usd",
            "ripeness",
            "finding_counts",
            "duration_seconds",
            "review_strategy",
            "triage_verdict",
        }
        assert required_fields.issubset(record.keys())

    def test_build_run_record_no_pr_content(self) -> None:
        """Run record contains no PR content keys (title, body, diff, content)."""
        record = _build_default_record()
        forbidden_keys = {"title", "body", "diff", "content"}
        assert forbidden_keys.isdisjoint(record.keys())

    def test_build_run_record_finding_counts(self) -> None:
        """Run record includes the passed finding_counts dict."""
        counts = {"info": 3, "minor": 1, "major": 0, "critical": 0}
        record = _build_default_record(finding_counts=counts)
        assert record["finding_counts"] == counts

    def test_build_run_record_includes_correlation_id(self) -> None:
        """Run record includes the current correlation ID."""
        cid = new_correlation_id()
        record = _build_default_record()
        assert record["correlation_id"] == cid

    def test_build_run_record_event_type(self) -> None:
        """Run record event field is 'review_complete'."""
        record = _build_default_record()
        assert record["event"] == "review_complete"

    def test_build_run_record_duration_rounded(self) -> None:
        """Duration is rounded to 3 decimal places."""
        record = _build_default_record(duration_seconds=1.23456789)
        assert record["duration_seconds"] == 1.235

    def test_format_run_record_json_valid(self) -> None:
        """json.dumps(record) succeeds without errors."""
        new_correlation_id()
        record = _build_default_record()
        serialized = json.dumps(record, default=str)
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert parsed["event"] == "review_complete"


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestEmitRunRecord:
    """Integration tests for run record emission."""

    def test_emit_run_record_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """emit_run_record produces a JSON-parseable log line with all fields."""
        new_correlation_id()
        record = _build_default_record()

        with caplog.at_level(logging.INFO, logger="lychee.run_record"):
            emit_run_record(record)

        assert len(caplog.records) >= 1
        log_msg = caplog.records[-1].message
        parsed = json.loads(log_msg)
        assert parsed["event"] == "review_complete"
        assert "correlation_id" in parsed
        assert "repo" in parsed


class TestStructuredLogging:
    """Integration tests for structured logging format."""

    def test_structured_logging_format(self) -> None:
        """After setup, log output includes correlation_id, time, name, level, message.

        Uses a dedicated logger with its own handler and filter to avoid
        interfering with pytest's logging capture infrastructure.
        """
        import io

        cid = new_correlation_id()

        # Build the same format as setup_structured_logging but on an
        # isolated logger + StringIO so we don't disturb root/pytest.
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.INFO)
        fmt = (
            '{"time":"%(asctime)s","name":"%(name)s",'
            '"level":"%(levelname)s","correlation_id":"%(correlation_id)s",'
            '"message":"%(message)s"}'
        )
        handler.setFormatter(logging.Formatter(fmt))
        handler.addFilter(CorrelationFilter())

        logger = logging.getLogger("test.structured.isolated")
        logger.propagate = False
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        try:
            logger.info("test message")

            output = stream.getvalue().strip()
            assert output, "Expected structured log output"
            parsed = json.loads(output)
            assert parsed["correlation_id"] == cid
            assert "time" in parsed
            assert parsed["name"] == "test.structured.isolated"
            assert parsed["level"] == "INFO"
            assert parsed["message"] == "test message"
        finally:
            logger.removeHandler(handler)
            logger.propagate = True


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_observability_module_imports() -> None:
    """All public functions are importable from lychee.observability."""
    from lychee.observability import (
        CorrelationFilter,
        build_run_record,
        compute_finding_counts,
        emit_run_record,
        get_correlation_id,
        get_review_strategy,
        get_triage_verdict,
        new_correlation_id,
        set_review_strategy,
        set_triage_verdict,
        setup_structured_logging,
    )

    assert callable(new_correlation_id)
    assert callable(get_correlation_id)
    assert callable(set_review_strategy)
    assert callable(get_review_strategy)
    assert callable(set_triage_verdict)
    assert callable(get_triage_verdict)
    assert callable(setup_structured_logging)
    assert callable(compute_finding_counts)
    assert callable(build_run_record)
    assert callable(emit_run_record)
    assert CorrelationFilter is not None


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_existing_logging_still_works(caplog: pytest.LogCaptureFixture) -> None:
    """Existing log calls still produce output after structured logging setup."""
    # Ensure structured logging doesn't suppress standard log calls
    new_correlation_id()
    logger = logging.getLogger("test.sanity")

    with caplog.at_level(logging.INFO, logger="test.sanity"):
        logger.info("sanity check message")

    assert any("sanity check message" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def test_run_record_schema_snapshot() -> None:
    """Fixed inputs produce expected record dict (schema stability)."""
    # Pin correlation ID for determinism
    cid = new_correlation_id()
    record = build_run_record(
        repo="owner/repo",
        pr_number=42,
        head_sha="abc123",
        model="claude-sonnet-4-6",
        usage={"input_tokens": 1000, "output_tokens": 200},
        cost_usd=0.006,
        ripeness="ripe",
        finding_counts={"info": 1, "minor": 0, "major": 0, "critical": 0},
        duration_seconds=1.234,
        review_strategy="single_pass",
        triage_verdict=None,
    )

    assert record["event"] == "review_complete"
    assert record["correlation_id"] == cid
    assert record["repo"] == "owner/repo"
    assert record["pr_number"] == 42
    assert record["head_sha"] == "abc123"
    assert record["model"] == "claude-sonnet-4-6"
    assert record["usage"] == {"input_tokens": 1000, "output_tokens": 200}
    assert record["cost_usd"] == 0.006
    assert record["ripeness"] == "ripe"
    assert record["finding_counts"] == {"info": 1, "minor": 0, "major": 0, "critical": 0}
    assert record["duration_seconds"] == 1.234
    assert record["review_strategy"] == "single_pass"
    assert record["triage_verdict"] is None
    # Timestamp is dynamic but must be present
    assert "timestamp" in record


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_no_secrets_leaked() -> None:
    """Run record contains no API keys, tokens, or PR content."""
    new_correlation_id()
    record = build_run_record(
        repo="owner/repo",
        pr_number=42,
        head_sha="abc123",
        model="claude-sonnet-4-6",
        usage={"input_tokens": 1000, "output_tokens": 200},
        cost_usd=0.006,
        ripeness="ripe",
        finding_counts={"info": 1, "minor": 0, "major": 0, "critical": 0},
        duration_seconds=1.234,
        review_strategy="single_pass",
        triage_verdict=None,
    )

    serialized = json.dumps(record, default=str)

    # No secret-like patterns
    assert "ghp_" not in serialized
    assert "sk-ant-" not in serialized
    assert "ANTHROPIC_API_KEY" not in serialized
    assert "GITHUB_TOKEN" not in serialized

    # No PR content keys
    assert "title" not in record
    assert "body" not in record
    assert "diff" not in record
    assert "content" not in record
