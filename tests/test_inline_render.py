"""Unit, smoke, sanity, regression, and acceptance tests for lychee.inline_render.

Covers render_inline_comment(), render_suggestion_block(), and the
SEVERITY_LABELS / _SEVERITY_EMOJI mappings.

Framework: pytest.  Coverage target: >= 90% on src/lychee/inline_render.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lychee.inline_render import SEVERITY_LABELS, render_inline_comment, render_suggestion_block
from lychee.models import Category, Finding, Severity

FIXTURES_DIR: Path = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    severity: Severity = Severity.minor,
    category: Category = Category.style,
    message: str = "Trailing whitespace.",
    suggestion: str | None = None,
) -> Finding:
    """Build a Finding with sensible defaults for inline-render tests."""
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
    from lychee.inline_render import (
        SEVERITY_LABELS,
        render_inline_comment,
        render_suggestion_block,
    )

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


def test_render_inline_comment_non_empty() -> None:
    """render_inline_comment always returns a non-empty string for any valid Finding."""
    for sev in Severity:
        for cat in Category:
            finding = _make_finding(severity=sev, category=cat)
            result = render_inline_comment(finding)
            assert result, f"Empty output for severity={sev}, category={cat}"


# ---------------------------------------------------------------------------
# Unit tests — render_inline_comment
# ---------------------------------------------------------------------------


def test_basic_rendering() -> None:
    """Basic finding renders with emoji, severity label, category, and message."""
    finding = _make_finding()
    result = render_inline_comment(finding)
    assert "**[Minor]**" in result
    assert "(*style*)" in result
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
        (Severity.info, "**[Info]**"),
        (Severity.minor, "**[Minor]**"),
        (Severity.major, "**[Major]**"),
        (Severity.critical, "**[Critical]**"),
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
        (Severity.info, "\u2139\ufe0f"),
        (Severity.minor, "\u26a0\ufe0f"),
        (Severity.major, "\U0001f536"),
        (Severity.critical, "\U0001f534"),
    ],
)
def test_all_severity_emojis(severity: Severity, expected_emoji: str) -> None:
    """Each severity renders its correct emoji."""
    finding = _make_finding(severity=severity)
    result = render_inline_comment(finding)
    assert expected_emoji in result


@pytest.mark.parametrize(
    "category",
    list(Category),
)
def test_all_categories(category: Category) -> None:
    """Each category value appears in the rendered output."""
    finding = _make_finding(category=category)
    result = render_inline_comment(finding)
    assert f"(*{category.value}*)" in result


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


def test_suggestion_block_strips_trailing_whitespace() -> None:
    """Trailing whitespace on each line is stripped inside the suggestion block."""
    suggestion = "x = 1   \ny = 2\t\nz = 3"
    result = render_suggestion_block(suggestion)
    assert result == "```suggestion\nx = 1\ny = 2\nz = 3\n```"


def test_suggestion_block_no_extra_blank_lines() -> None:
    """Leading and trailing blank lines inside the fence are stripped."""
    suggestion = "\n\nx = 1\ny = 2\n\n"
    result = render_suggestion_block(suggestion)
    # No blank lines between opening fence and first content, or
    # between last content and closing fence.
    lines = result.split("\n")
    assert lines[0] == "```suggestion"
    assert lines[1] == "x = 1"
    assert lines[-2] == "y = 2"
    assert lines[-1] == "```"


def test_suggestion_block_empty_string_defense() -> None:
    """An empty suggestion string returns an empty string (defensive guard)."""
    assert render_suggestion_block("") == ""


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def test_deterministic_output() -> None:
    """render_inline_comment produces identical output on consecutive calls."""
    finding = _make_finding(suggestion="fix()")
    assert render_inline_comment(finding) == render_inline_comment(finding)


def test_inline_comment_with_suggestion_snapshot() -> None:
    """Golden snapshot: rendered comment with a suggestion block."""
    finding = Finding(
        file="src/auth.py",
        line=42,
        severity=Severity.major,
        category=Category.security,
        message="SQL injection via unsanitized input.",
        suggestion="cursor.execute(query, (user_input,))",
    )
    result = render_inline_comment(finding)
    expected = (FIXTURES_DIR / "golden_inline_with_suggestion.md").read_text(encoding="utf-8")
    assert result == expected.rstrip("\n")


def test_inline_comment_without_suggestion_snapshot() -> None:
    """Golden snapshot: rendered comment without a suggestion block."""
    finding = Finding(
        file="src/utils.py",
        line=10,
        severity=Severity.minor,
        category=Category.style,
        message="Trailing whitespace.",
    )
    result = render_inline_comment(finding)
    expected = (FIXTURES_DIR / "golden_inline_without_suggestion.md").read_text(encoding="utf-8")
    assert result == expected.rstrip("\n")


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


def test_accept_suggestions_render_as_appliable() -> None:
    """A finding with a suggestion produces the exact GitHub one-click-apply syntax."""
    finding = _make_finding(suggestion="fixed = True")
    result = render_inline_comment(finding)
    assert "```suggestion\nfixed = True\n```" in result


def test_accept_absent_suggestion_no_block() -> None:
    """A finding without a suggestion produces no suggestion fence at all."""
    finding = _make_finding(suggestion=None)
    result = render_inline_comment(finding)
    assert "```suggestion" not in result
    assert "suggestion" not in result.lower() or "suggestion" not in result.split("```")


# ---------------------------------------------------------------------------
# UI tests
# ---------------------------------------------------------------------------


def test_suggestion_block_exact_syntax() -> None:
    """Suggestion block uses GitHub's exact ```suggestion``` syntax."""
    result = render_suggestion_block("code")
    assert result.startswith("```suggestion\n")
    assert result.endswith("\n```")


def test_ui_inline_comment_valid_markdown() -> None:
    """Rendered body is well-formed GitHub-flavored markdown.

    Checks that bold markers and italic markers are balanced, and that
    code fences (if present) are balanced.
    """
    finding = _make_finding(suggestion="fix()")
    result = render_inline_comment(finding)

    # Bold markers (**) should appear in pairs.
    bold_count = result.count("**")
    assert bold_count % 2 == 0, f"Unbalanced bold markers: {bold_count}"

    # Italic markers (*) outside bold should be balanced.
    # Remove bold markers first, then count remaining single *.
    without_bold = result.replace("**", "")
    star_count = without_bold.count("*")
    assert star_count % 2 == 0, f"Unbalanced italic markers: {star_count}"

    # Code fences should be balanced.
    fence_count = result.count("```")
    assert fence_count % 2 == 0, f"Unbalanced code fences: {fence_count}"


def test_severity_labels_include_text_not_just_emoji() -> None:
    """Severity labels in output include textual labels, not just emojis."""
    for sev in Severity:
        finding = _make_finding(severity=sev)
        result = render_inline_comment(finding)
        assert SEVERITY_LABELS[sev] in result


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_inline_comment_with_real_finding_model() -> None:
    """Construct a Finding via Pydantic and render it; verify well-formed output.

    This exercises the full path from model construction through rendering,
    ensuring Pydantic validation and the renderer work together correctly.
    """
    finding = Finding(
        file="src/auth.py",
        line=15,
        severity=Severity.critical,
        category=Category.security,
        message="Hardcoded secret in source code.",
        suggestion='secret = os.environ["API_KEY"]',
    )
    result = render_inline_comment(finding)
    assert "**[Critical]**" in result
    assert "(*security*)" in result
    assert "Hardcoded secret in source code." in result
    assert "```suggestion" in result
    assert 'secret = os.environ["API_KEY"]' in result


def test_inline_comment_integrated_with_diff_position() -> None:
    """Rendered comment body is suitable for the GitHub review API.

    Given a Finding and a DiffPosition, the rendered body should contain
    only severity, category, message, and suggestion — no file/line info,
    since position is conveyed separately via the API's path/position fields.
    """
    from lychee.diff_mapping import DiffPosition

    finding = Finding(
        file="src/utils.py",
        line=42,
        severity=Severity.minor,
        category=Category.performance,
        message="Unnecessary list copy in loop.",
        suggestion="for item in items:",
    )
    _pos = DiffPosition(path="src/utils.py", position=10, head_line=42)
    body = render_inline_comment(finding)

    # Body should NOT contain file path or line number — those are
    # conveyed via the GitHub API's path and position fields.
    assert "src/utils.py" not in body
    assert "line 42" not in body
    assert ":42" not in body

    # Body should contain the meaningful review content.
    assert "**[Minor]**" in body
    assert "(*performance*)" in body
    assert "Unnecessary list copy in loop." in body
    assert "```suggestion\nfor item in items:\n```" in body
