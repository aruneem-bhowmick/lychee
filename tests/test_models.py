"""Unit and regression tests for lychee.models domain types.

Covers enum correctness, Finding and ReviewResult construction, field
validation rules, serialization round-trips, the submit_review tool
schema, and the from_tool_input / to_tool_schema methods.
"""

import json
from pathlib import Path

import pydantic
import pytest

from lychee.models import Category, Finding, ReviewResult, Ripeness, Severity

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(**kwargs: object) -> Finding:
    """Return a minimal valid Finding, overriding any fields via kwargs."""
    defaults: dict[str, object] = {
        "file": "src/main.py",
        "severity": Severity.minor,
        "category": Category.style,
        "message": "A test finding.",
    }
    defaults.update(kwargs)
    return Finding(**defaults)  # type: ignore[arg-type]


def _make_review_result(**kwargs: object) -> ReviewResult:
    """Return a minimal valid ReviewResult, overriding any fields via kwargs."""
    defaults: dict[str, object] = {
        "ripeness": Ripeness.ripe,
        "summary": "Looks good.",
        "walkthrough": "## Summary\nAll changes are minimal.",
        "findings": [],
        "model": "claude-sonnet-4-6",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }
    defaults.update(kwargs)
    return ReviewResult(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def test_models_import() -> None:
    """All domain types import cleanly from lychee.models."""
    from lychee.models import (  # noqa: F401
        Category,
        Finding,
        ReviewResult,
        Ripeness,
        Severity,
    )

    assert Severity and Ripeness and Category and Finding and ReviewResult


# ---------------------------------------------------------------------------
# Enum unit tests
# ---------------------------------------------------------------------------


def test_severity_values() -> None:
    """Severity enum has all four members with correct string values."""
    assert Severity.info.value == "info"
    assert Severity.minor.value == "minor"
    assert Severity.major.value == "major"
    assert Severity.critical.value == "critical"


def test_ripeness_values() -> None:
    """Ripeness enum has all three members with correct string values."""
    assert Ripeness.ripe.value == "ripe"
    assert Ripeness.unripe.value == "unripe"
    assert Ripeness.sour.value == "sour"


def test_category_values() -> None:
    """Category enum has all seven members with correct string values."""
    expected = {
        "correctness",
        "security",
        "performance",
        "tests",
        "style",
        "docs",
        "other",
    }
    assert {m.value for m in Category} == expected


# ---------------------------------------------------------------------------
# Finding unit tests
# ---------------------------------------------------------------------------


def test_finding_construction_minimal() -> None:
    """Finding constructs with only required fields and correct default values."""
    f = Finding(
        file="a.py",
        severity=Severity.info,
        category=Category.correctness,
        message="A problem.",
    )
    assert f.file == "a.py"
    assert f.line is None
    assert f.severity == Severity.info
    assert f.category == Category.correctness
    assert f.message == "A problem."
    assert f.suggestion is None


def test_finding_construction_full() -> None:
    """Finding accepts all fields including line and suggestion."""
    f = Finding(
        file="b.py",
        line=42,
        severity=Severity.major,
        category=Category.security,
        message="SQL injection risk.",
        suggestion="Use parameterized queries.",
    )
    assert f.line == 42
    assert f.suggestion == "Use parameterized queries."


def test_finding_rejects_empty_suggestion() -> None:
    """Finding raises ValidationError when suggestion is an empty string."""
    with pytest.raises(pydantic.ValidationError):
        Finding(
            file="a.py",
            severity=Severity.info,
            category=Category.style,
            message="msg",
            suggestion="",
        )


def test_finding_rejects_unknown_field() -> None:
    """Finding raises ValidationError when an extra unknown key is provided."""
    with pytest.raises(pydantic.ValidationError):
        Finding(  # type: ignore[call-arg]
            file="a.py",
            severity=Severity.info,
            category=Category.style,
            message="msg",
            unknown_field="oops",
        )


def test_finding_frozen() -> None:
    """Finding raises ValidationError when mutation is attempted on a frozen model."""
    f = _make_finding()
    with pytest.raises(pydantic.ValidationError):
        f.file = "mutated.py"  # type: ignore[misc]


def test_line_zero_accepted() -> None:
    """Finding accepts line=0 as a valid 0-indexed line number."""
    f = _make_finding(line=0)
    assert f.line == 0


def test_line_none_accepted() -> None:
    """Finding accepts line=None to represent a file-level finding."""
    f = _make_finding(line=None)
    assert f.line is None


# ---------------------------------------------------------------------------
# ReviewResult unit tests
# ---------------------------------------------------------------------------


def test_review_result_construction_minimal() -> None:
    """ReviewResult constructs successfully with an empty findings list."""
    r = _make_review_result(findings=[])
    assert r.findings == []
    assert r.ripeness == Ripeness.ripe


def test_review_result_construction_full() -> None:
    """ReviewResult constructs correctly with all fields populated."""
    f = _make_finding()
    r = _make_review_result(findings=[f])
    assert len(r.findings) == 1
    assert r.findings[0] is f


def test_review_result_rejects_empty_summary() -> None:
    """ReviewResult raises ValidationError when summary is an empty string."""
    with pytest.raises(pydantic.ValidationError):
        _make_review_result(summary="")


def test_review_result_rejects_empty_walkthrough() -> None:
    """ReviewResult raises ValidationError when walkthrough is an empty string."""
    with pytest.raises(pydantic.ValidationError):
        _make_review_result(walkthrough="")


def test_review_result_rejects_empty_model() -> None:
    """ReviewResult raises ValidationError when model is an empty string."""
    with pytest.raises(pydantic.ValidationError):
        _make_review_result(model="")


def test_review_result_rejects_unknown_field() -> None:
    """ReviewResult raises ValidationError when extra unknown fields are provided."""
    with pytest.raises(pydantic.ValidationError):
        ReviewResult(  # type: ignore[call-arg]
            ripeness=Ripeness.ripe,
            summary="ok",
            walkthrough="ok",
            findings=[],
            model="claude-sonnet-4-6",
            usage={},
            extra_field="oops",
        )


# ---------------------------------------------------------------------------
# from_tool_input tests
# ---------------------------------------------------------------------------


def test_from_tool_input_valid() -> None:
    """from_tool_input round-trips: construct, dump, reload, and assert equality."""
    original = _make_review_result()
    data = original.model_dump()
    restored = ReviewResult.from_tool_input(data)
    assert restored == original


def test_from_tool_input_invalid_severity() -> None:
    """from_tool_input raises ValidationError for an unknown severity value."""
    data = _make_review_result().model_dump()
    data["findings"] = [
        {
            "file": "a.py",
            "severity": "blocker",
            "category": "style",
            "message": "oops",
        }
    ]
    with pytest.raises(pydantic.ValidationError):
        ReviewResult.from_tool_input(data)


def test_from_tool_input_missing_required() -> None:
    """from_tool_input raises ValidationError when the ripeness field is absent."""
    data = _make_review_result().model_dump()
    del data["ripeness"]
    with pytest.raises(pydantic.ValidationError):
        ReviewResult.from_tool_input(data)


def test_from_tool_input_invalid_ripeness() -> None:
    """from_tool_input raises ValidationError for an invalid ripeness value."""
    data = _make_review_result().model_dump()
    data["ripeness"] = "maybe"
    with pytest.raises(pydantic.ValidationError):
        ReviewResult.from_tool_input(data)


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------


def test_model_dump_lossless() -> None:
    """model_dump() round-trips back to an identical ReviewResult."""
    original = _make_review_result()
    d = original.model_dump()
    assert ReviewResult.model_validate(d) == original


def test_model_dump_json_lossless() -> None:
    """model_dump_json() round-trips back to an identical ReviewResult via JSON."""
    original = _make_review_result()
    s = original.model_dump_json()
    assert ReviewResult.model_validate_json(s) == original


# ---------------------------------------------------------------------------
# Sanity test
# ---------------------------------------------------------------------------


def test_minimal_review_result_constructs() -> None:
    """Simplest valid ReviewResult (no findings, ripe, non-empty fields) constructs."""
    r = ReviewResult(
        ripeness=Ripeness.ripe,
        summary="ok",
        walkthrough="ok",
        findings=[],
        model="test-model",
        usage={},
    )
    assert r.ripeness == Ripeness.ripe


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_round_trip_lossless() -> None:
    """Serializing and deserializing a ReviewResult produces an identical object."""
    f = _make_finding(line=10, suggestion="Fix this.")
    original = _make_review_result(findings=[f])
    data = original.model_dump()
    restored = ReviewResult.from_tool_input(data)
    assert restored == original


def test_accept_invalid_payload_raises_typed_error() -> None:
    """A malformed payload raises pydantic.ValidationError, not a generic exception."""
    with pytest.raises(pydantic.ValidationError):
        ReviewResult.from_tool_input(
            {
                "ripeness": "bad_value",
                "summary": "ok",
                "walkthrough": "ok",
                "findings": [],
                "model": "m",
                "usage": {},
            }
        )


def test_accept_schema_matches_spec() -> None:
    """The submit_review tool schema includes all required fields."""
    schema = ReviewResult.to_tool_schema()
    assert schema["name"] == "submit_review"
    assert "description" in schema
    assert "input_schema" in schema
    props = schema["input_schema"].get("properties", {})
    for field in ("ripeness", "summary", "walkthrough", "findings", "model", "usage"):
        assert field in props, f"Field '{field}' missing from submit_review schema"


# ---------------------------------------------------------------------------
# Regression snapshot test
# ---------------------------------------------------------------------------


def test_submit_review_schema_snapshot() -> None:
    """to_tool_schema() output matches the golden snapshot in tests/fixtures/."""
    schema = ReviewResult.to_tool_schema()
    serialized = json.dumps(schema, sort_keys=True, indent=2)

    snapshot_path = FIXTURES_DIR / "submit_review_schema.json"
    if not snapshot_path.exists():
        snapshot_path.write_text(serialized, encoding="utf-8")
        return

    saved = snapshot_path.read_text(encoding="utf-8")
    assert serialized == saved, (
        "submit_review schema changed. If intentional, delete "
        "tests/fixtures/submit_review_schema.json and re-run to regenerate."
    )
