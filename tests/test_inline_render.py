"""Unit, smoke, sanity, regression, and acceptance tests for lychee.inline_render.

Covers render_inline_comment(), render_suggestion_block(), and the
SEVERITY_LABELS / _SEVERITY_EMOJI mappings.

Framework: pytest.  Coverage target: >= 90% on src/lychee/inline_render.py.
"""

from __future__ import annotations

import pytest

from lychee.inline_render import SEVERITY_LABELS, render_inline_comment, render_suggestion_block
from lychee.models import Category, Finding, Severity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    severity: Severity = Severity.minor,
    category: Category = Category.style,
    message: str = "Trailing whitespace.",
    suggestion: str | None = None,
) -> Finding:
    return Finding(
        file="src/app.py",
        line=10,
        severity=severity,
        category=category,
        message=message,
        suggestion=suggestion,
    )


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_imports() -> None:
    """All public names import cleanly from lychee.inline_render."""
    from lychee.inline_render import SEVERITY_LABELS, render_inline_comment, render_suggestion_block

    assert callable(render_inline_comment)
    assert callable(render_suggestion_block)
    assert isinstance(SEVERITY_LABELS, dict)


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_severity_labels_cover_all_values() -> None:
    """SEVERITY_LABELS has an entry for every Severity enum member."""
    for sev in Severity:
        assert sev in SEVERITY_LABELS, f"Missing label for {sev}"


# ---------------------------------------------------------------------------
# Unit tests — render_inline_comment
# ---------------------------------------------------------------------------


def test_basic_rendering() -> None:
    """Basic finding renders with emoji, severity label, category, and message."""
    finding = _make_finding()
    result = render_inline_comment(finding)
    assert "**Minor**" in result
    assert "[style]" in result
    assert "Trailing whitespace." in result


def test_rendering_without_suggestion() -> None:
    """Finding without suggestion has no suggestion block."""
    finding = _make_finding(suggestion=None)
    result = render_inline_comment(finding)
    assert "```suggestion" not in result


def test_rendering_with_suggestion() -> None:
    """Finding with suggestion includes a suggestion block."""
    finding = _make_finding(suggestion="fixed_code()")
    result = render_inline_comment(finding)
    assert "```suggestion" in result
    assert "fixed_code()" in result


@pytest.mark.parametrize(
    ("severity", "expected_label"),
    [
        (Severity.info, "**Info**"),
        (Severity.minor, "**Minor**"),
        (Severity.major, "**Major**"),
        (Severity.critical, "**Critical**"),
    ],
)
def test_all_severities(severity: Severity, expected_label: str) -> None:
    """Each severity renders its correct label."""
    finding = _make_finding(severity=severity)
    result = render_inline_comment(finding)
    assert expected_label in result


@pytest.mark.parametrize(
    ("severity", "expected_emoji"),
    [
        (Severity.info, "ℹ️"),  # noqa: RUF001
        (Severity.minor, "⚠️"),
        (Severity.major, "🔶"),
        (Severity.critical, "🔴"),
    ],
)
def test_all_severity_emojis(severity: Severity, expected_emoji: str) -> None:
    """Each severity renders its correct emoji."""
    finding = _make_finding(severity=severity)
    result = render_inline_comment(finding)
    assert expected_emoji in result


# ---------------------------------------------------------------------------
# Unit tests — render_suggestion_block
# ---------------------------------------------------------------------------


def test_suggestion_block_single_line() -> None:
    """Single-line suggestion is wrapped correctly."""
    result = render_suggestion_block("x = 1")
    assert result == "```suggestion\nx = 1\n```"


def test_suggestion_block_multi_line() -> None:
    """Multi-line suggestion preserves all lines."""
    suggestion = "line1\nline2\nline3"
    result = render_suggestion_block(suggestion)
    assert result == "```suggestion\nline1\nline2\nline3\n```"


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def test_deterministic_output() -> None:
    """render_inline_comment produces identical output on consecutive calls."""
    finding = _make_finding(suggestion="fix()")
    assert render_inline_comment(finding) == render_inline_comment(finding)


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_valid_markdown_balanced_fences() -> None:
    """Output with suggestion has balanced backtick fences."""
    finding = _make_finding(suggestion="fix()")
    result = render_inline_comment(finding)
    fence_count = result.count("```")
    assert fence_count % 2 == 0, f"Odd fence count: {fence_count}"


def test_no_suggestion_no_fences() -> None:
    """Output without suggestion has zero backtick fences."""
    finding = _make_finding(suggestion=None)
    result = render_inline_comment(finding)
    assert "```" not in result


# ---------------------------------------------------------------------------
# UI tests
# ---------------------------------------------------------------------------


def test_suggestion_block_exact_syntax() -> None:
    """Suggestion block uses GitHub's exact ```suggestion``` syntax."""
    result = render_suggestion_block("code")
    assert result.startswith("```suggestion\n")
    assert result.endswith("\n```")


def test_severity_labels_include_text_not_just_emoji() -> None:
    """Severity labels in output include textual labels, not just emojis."""
    for sev in Severity:
        finding = _make_finding(severity=sev)
        result = render_inline_comment(finding)
        assert SEVERITY_LABELS[sev] in result
