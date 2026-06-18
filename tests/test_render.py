"""Unit, smoke, sanity, regression, and acceptance tests for lychee.render.

Covers render_comment() and all private helpers.  The four golden snapshot
files in tests/fixtures/ are the primary UI verification surface: any
change to rendered output requires a deliberate update to those files.

Framework: pytest.  Coverage target: >= 90% on src/lychee/render.py.
"""

from pathlib import Path

import pytest

from lychee.models import Category, Finding, ReviewResult, Ripeness, Severity
from lychee.render import REVIEW_MARKER, render_comment, severity_at_or_above

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_valid_review_result() -> ReviewResult:
    """Minimal valid ReviewResult: ripe, no findings, short text fields."""
    return ReviewResult(
        ripeness=Ripeness.ripe,
        summary="Looks good.",
        walkthrough="All changes are minimal.",
        findings=[],
        model="test-model",
        usage={},
    )


@pytest.fixture
def ripe_result_fixture() -> ReviewResult:
    """Ripe ReviewResult with one minor and one info finding, no suggestions."""
    return ReviewResult(
        ripeness=Ripeness.ripe,
        summary="This PR looks good overall with minor style issues.",
        walkthrough="## Changes\n\nAdded utility functions and updated main module.",
        findings=[
            Finding(
                file="src/main.py",
                line=42,
                severity=Severity.minor,
                category=Category.style,
                message="Trailing whitespace.",
            ),
            Finding(
                file="src/utils.py",
                line=None,
                severity=Severity.info,
                category=Category.docs,
                message="Missing module docstring.",
            ),
        ],
        model="claude-sonnet-4-6",
        usage={"input_tokens": 1000, "output_tokens": 200},
    )


@pytest.fixture
def unripe_result_fixture() -> ReviewResult:
    """Unripe ReviewResult with one major finding that carries a suggestion."""
    return ReviewResult(
        ripeness=Ripeness.unripe,
        summary=("This PR has a significant security issue that must be addressed before merging."),
        walkthrough="## Review\n\nThe authentication module needs improvement.",
        findings=[
            Finding(
                file="src/auth.py",
                line=15,
                severity=Severity.major,
                category=Category.security,
                message="Password stored in plaintext.",
                suggestion="hash_password(password)",
            ),
        ],
        model="claude-sonnet-4-6",
        usage={"input_tokens": 1500, "output_tokens": 300},
    )


@pytest.fixture
def sour_result_fixture() -> ReviewResult:
    """Sour ReviewResult with critical and minor findings, no suggestions."""
    return ReviewResult(
        ripeness=Ripeness.sour,
        summary=("This PR introduces critical security vulnerabilities and must not be merged."),
        walkthrough="## Review\n\nThe database module has severe issues.",
        findings=[
            Finding(
                file="src/database.py",
                line=7,
                severity=Severity.critical,
                category=Category.correctness,
                message="SQL injection vulnerability.",
            ),
            Finding(
                file="src/database.py",
                line=25,
                severity=Severity.minor,
                category=Category.style,
                message="Variable name should be snake_case.",
            ),
        ],
        model="claude-sonnet-4-6",
        usage={"input_tokens": 2000, "output_tokens": 400},
    )


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_render_module_imports() -> None:
    """render_comment and REVIEW_MARKER import cleanly from lychee.render."""
    from lychee.render import REVIEW_MARKER, render_comment

    assert callable(render_comment)
    assert isinstance(REVIEW_MARKER, str)


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_minimal_render_does_not_crash(
    minimal_valid_review_result: ReviewResult,
) -> None:
    """render_comment on a minimal valid ReviewResult returns a non-empty string."""
    output = render_comment(minimal_valid_review_result)
    assert isinstance(output, str) and len(output) > 0


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_marker_present(minimal_valid_review_result: ReviewResult) -> None:
    """Rendered output contains the hidden lychee:review marker."""
    output = render_comment(minimal_valid_review_result)
    assert "<!-- lychee:review -->" in output


def test_ripe_badge(minimal_valid_review_result: ReviewResult) -> None:
    """Ripe ripeness renders the green badge text."""
    output = render_comment(minimal_valid_review_result)
    assert "🟢 **Ripe**" in output


def test_unripe_badge(unripe_result_fixture: ReviewResult) -> None:
    """Unripe ripeness renders the yellow badge text."""
    output = render_comment(unripe_result_fixture)
    assert "🟡 **Unripe**" in output


def test_sour_badge(sour_result_fixture: ReviewResult) -> None:
    """Sour ripeness renders the red badge text."""
    output = render_comment(sour_result_fixture)
    assert "🔴 **Sour**" in output


def test_model_name_in_header(ripe_result_fixture: ReviewResult) -> None:
    """The ReviewResult model name appears in the rendered output."""
    output = render_comment(ripe_result_fixture)
    assert ripe_result_fixture.model in output


def test_summary_in_output(ripe_result_fixture: ReviewResult) -> None:
    """The summary (Nectar) text appears verbatim in the rendered output."""
    output = render_comment(ripe_result_fixture)
    assert ripe_result_fixture.summary in output


def test_walkthrough_in_output(ripe_result_fixture: ReviewResult) -> None:
    """The walkthrough (The Peel) text appears verbatim in the rendered output."""
    output = render_comment(ripe_result_fixture)
    assert ripe_result_fixture.walkthrough in output


def test_footer_present(minimal_valid_review_result: ReviewResult) -> None:
    """The footer tag line appears in every rendered output."""
    output = render_comment(minimal_valid_review_result)
    assert "Reviewed to the core by Lychee" in output


def test_no_findings_renders_clean(
    minimal_valid_review_result: ReviewResult,
) -> None:
    """An empty findings list renders the clean-PR message."""
    output = render_comment(minimal_valid_review_result)
    assert "No pits found" in output


def test_finding_file_and_message(ripe_result_fixture: ReviewResult) -> None:
    """Each finding's file path and message appear in the rendered output."""
    output = render_comment(ripe_result_fixture)
    for finding in ripe_result_fixture.findings:
        assert finding.file in output
        assert finding.message in output


def test_finding_with_line(ripe_result_fixture: ReviewResult) -> None:
    """A finding with line=42 produces 'line 42' in the rendered output."""
    output = render_comment(ripe_result_fixture)
    assert "line 42" in output


def test_finding_without_line(ripe_result_fixture: ReviewResult) -> None:
    """A finding with line=None produces no line reference in the output."""
    # Use only the file-level finding (line=None) in isolation.
    no_line_finding = ripe_result_fixture.findings[1]
    assert no_line_finding.line is None
    result = ReviewResult(
        ripeness=Ripeness.ripe,
        summary="ok",
        walkthrough="ok",
        findings=[no_line_finding],
        model="test-model",
        usage={},
    )
    output = render_comment(result)
    assert "line" not in output


def test_finding_with_suggestion(unripe_result_fixture: ReviewResult) -> None:
    """A finding with a suggestion renders a GitHub suggestion fence block."""
    output = render_comment(unripe_result_fixture)
    assert "```suggestion" in output


def test_finding_without_suggestion(ripe_result_fixture: ReviewResult) -> None:
    """Findings with no suggestion produce no suggestion fence in the output."""
    output = render_comment(ripe_result_fixture)
    assert "```suggestion" not in output


def test_severity_order(sour_result_fixture: ReviewResult) -> None:
    """Critical group appears before minor group in the rendered output."""
    output = render_comment(sour_result_fixture)
    assert output.index("### Critical") < output.index("### Minor")


def test_empty_severity_group_skipped(sour_result_fixture: ReviewResult) -> None:
    """Severity groups with no findings produce no heading in the output."""
    output = render_comment(sour_result_fixture)
    assert "### Major" not in output


def test_cost_line_present(minimal_valid_review_result: ReviewResult) -> None:
    """A provided cost_line appears in the output before the footer."""
    cost = "💰 Cost: $0.003"
    output = render_comment(minimal_valid_review_result, cost_line=cost)
    assert cost in output
    assert output.index(cost) < output.index("*Reviewed to the core by Lychee*")


def test_cost_line_absent(minimal_valid_review_result: ReviewResult) -> None:
    """When cost_line=None, no cost content appears in the output."""
    output = render_comment(minimal_valid_review_result, cost_line=None)
    assert "💰 Cost" not in output


def test_deterministic(ripe_result_fixture: ReviewResult) -> None:
    """render_comment produces identical output on two consecutive calls."""
    assert render_comment(ripe_result_fixture) == render_comment(ripe_result_fixture)


def test_line_zero_renders(minimal_valid_review_result: ReviewResult) -> None:
    """A finding with line=0 produces 'line 0' in the rendered output."""
    finding = Finding(
        file="src/app.py",
        line=0,
        severity=Severity.info,
        category=Category.style,
        message="Line zero finding.",
    )
    result = ReviewResult(
        ripeness=Ripeness.ripe,
        summary="ok",
        walkthrough="ok",
        findings=[finding],
        model="test-model",
        usage={},
    )
    output = render_comment(result)
    assert "line 0" in output


def test_all_four_severities_rendered_in_order() -> None:
    """All four severity groups render in critical→major→minor→info order."""
    findings = [
        Finding(file="a.py", severity=Severity.info, category=Category.other, message="i"),
        Finding(file="b.py", severity=Severity.minor, category=Category.other, message="m"),
        Finding(file="c.py", severity=Severity.major, category=Category.other, message="M"),
        Finding(file="d.py", severity=Severity.critical, category=Category.other, message="C"),
    ]
    result = ReviewResult(
        ripeness=Ripeness.sour,
        summary="s",
        walkthrough="w",
        findings=findings,
        model="m",
        usage={},
    )
    output = render_comment(result)
    critical_pos = output.index("### Critical")
    major_pos = output.index("### Major")
    minor_pos = output.index("### Minor")
    info_pos = output.index("### Info")
    assert critical_pos < major_pos < minor_pos < info_pos


# ---------------------------------------------------------------------------
# Regression (golden snapshot) tests
# ---------------------------------------------------------------------------


def test_render_ripe_golden(ripe_result_fixture: ReviewResult) -> None:
    """Ripe ReviewResult output matches the golden snapshot exactly."""
    expected = (FIXTURES_DIR / "golden_ripe.md").read_text(encoding="utf-8")
    assert render_comment(ripe_result_fixture) == expected


def test_render_unripe_golden(unripe_result_fixture: ReviewResult) -> None:
    """Unripe ReviewResult output matches the golden snapshot exactly."""
    expected = (FIXTURES_DIR / "golden_unripe.md").read_text(encoding="utf-8")
    assert render_comment(unripe_result_fixture) == expected


def test_render_sour_golden(sour_result_fixture: ReviewResult) -> None:
    """Sour ReviewResult output matches the golden snapshot exactly."""
    expected = (FIXTURES_DIR / "golden_sour.md").read_text(encoding="utf-8")
    assert render_comment(sour_result_fixture) == expected


def test_render_no_findings_golden() -> None:
    """Ripe ReviewResult with no findings matches the golden snapshot exactly."""
    result = ReviewResult(
        ripeness=Ripeness.ripe,
        summary="This PR is clean with no issues found.",
        walkthrough="## Review\n\nAll changes are well-implemented.",
        findings=[],
        model="claude-sonnet-4-6",
        usage={"input_tokens": 800, "output_tokens": 150},
    )
    expected = (FIXTURES_DIR / "golden_no_findings.md").read_text(encoding="utf-8")
    assert render_comment(result) == expected


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_ripe_snapshot(ripe_result_fixture: ReviewResult) -> None:
    """Ripe result with findings matches the golden snapshot."""
    expected = (FIXTURES_DIR / "golden_ripe.md").read_text(encoding="utf-8")
    assert render_comment(ripe_result_fixture) == expected


def test_accept_unripe_snapshot(unripe_result_fixture: ReviewResult) -> None:
    """Unripe result with a suggestion matches the golden snapshot."""
    expected = (FIXTURES_DIR / "golden_unripe.md").read_text(encoding="utf-8")
    assert render_comment(unripe_result_fixture) == expected


def test_accept_sour_snapshot(sour_result_fixture: ReviewResult) -> None:
    """Sour result with critical and minor findings matches the golden snapshot."""
    expected = (FIXTURES_DIR / "golden_sour.md").read_text(encoding="utf-8")
    assert render_comment(sour_result_fixture) == expected


def test_accept_marker_present(
    minimal_valid_review_result: ReviewResult,
    ripe_result_fixture: ReviewResult,
    unripe_result_fixture: ReviewResult,
    sour_result_fixture: ReviewResult,
) -> None:
    """Every rendered output contains the hidden lychee:review marker."""
    for result in [
        minimal_valid_review_result,
        ripe_result_fixture,
        unripe_result_fixture,
        sour_result_fixture,
    ]:
        assert REVIEW_MARKER in render_comment(result)


def test_accept_valid_markdown(
    minimal_valid_review_result: ReviewResult,
    ripe_result_fixture: ReviewResult,
    unripe_result_fixture: ReviewResult,
    sour_result_fixture: ReviewResult,
) -> None:
    """Rendered output has an even number of triple-backtick fences (no unclosed blocks)."""
    for result in [
        minimal_valid_review_result,
        ripe_result_fixture,
        unripe_result_fixture,
        sour_result_fixture,
    ]:
        output = render_comment(result)
        fence_count = output.count("```")
        assert (
            fence_count % 2 == 0
        ), f"Odd backtick fence count {fence_count} for ripeness={result.ripeness}"


# ---------------------------------------------------------------------------
# Severity threshold filtering tests
# ---------------------------------------------------------------------------


@pytest.fixture
def multi_severity_result() -> ReviewResult:
    """ReviewResult with findings at all four severity levels."""
    return ReviewResult(
        ripeness=Ripeness.sour,
        summary="This PR has issues at multiple severity levels.",
        walkthrough="## Review\n\nMultiple severity levels present.",
        findings=[
            Finding(
                file="a.py",
                line=1,
                severity=Severity.critical,
                category=Category.security,
                message="Critical security issue.",
            ),
            Finding(
                file="b.py",
                line=10,
                severity=Severity.major,
                category=Category.correctness,
                message="Major logic bug.",
            ),
            Finding(
                file="c.py",
                line=20,
                severity=Severity.minor,
                category=Category.style,
                message="Minor style issue.",
            ),
            Finding(
                file="d.py",
                line=30,
                severity=Severity.info,
                category=Category.docs,
                message="Informational note.",
            ),
        ],
        model="claude-sonnet-4-6",
        usage={"input_tokens": 1000, "output_tokens": 200},
    )


def test_severity_threshold_info(multi_severity_result: ReviewResult) -> None:
    """Threshold 'info' keeps all findings."""
    output = render_comment(multi_severity_result, severity_threshold="info")
    assert "Critical security issue." in output
    assert "Major logic bug." in output
    assert "Minor style issue." in output
    assert "Informational note." in output


def test_severity_threshold_minor(multi_severity_result: ReviewResult) -> None:
    """Threshold 'minor' removes info findings."""
    output = render_comment(multi_severity_result, severity_threshold="minor")
    assert "Critical security issue." in output
    assert "Major logic bug." in output
    assert "Minor style issue." in output
    assert "Informational note." not in output


def test_severity_threshold_major(multi_severity_result: ReviewResult) -> None:
    """Threshold 'major' keeps only major and critical."""
    output = render_comment(multi_severity_result, severity_threshold="major")
    assert "Critical security issue." in output
    assert "Major logic bug." in output
    assert "Minor style issue." not in output
    assert "Informational note." not in output


def test_severity_threshold_critical(multi_severity_result: ReviewResult) -> None:
    """Threshold 'critical' keeps only critical findings."""
    output = render_comment(multi_severity_result, severity_threshold="critical")
    assert "Critical security issue." in output
    assert "Major logic bug." not in output
    assert "Minor style issue." not in output
    assert "Informational note." not in output


def test_severity_threshold_empty_after_filter(multi_severity_result: ReviewResult) -> None:
    """When all findings are below threshold, shows 'No pits found'."""
    # Create a result with only info findings
    result = ReviewResult(
        ripeness=Ripeness.ripe,
        summary="OK.",
        walkthrough="No issues.",
        findings=[
            Finding(
                file="x.py",
                severity=Severity.info,
                category=Category.docs,
                message="Just a note.",
            ),
        ],
        model="test-model",
        usage={},
    )
    output = render_comment(result, severity_threshold="minor")
    assert "No pits found" in output


def test_render_comment_with_threshold(multi_severity_result: ReviewResult) -> None:
    """Integration: full render with threshold produces valid markdown."""
    output = render_comment(multi_severity_result, severity_threshold="major")
    assert REVIEW_MARKER in output
    assert "## 🍯 Nectar" in output
    assert "## 🪨 Pits" in output
    # Only critical and major headings should be present
    assert "### Critical" in output
    assert "### Major" in output
    assert "### Minor" not in output
    assert "### Info" not in output


def test_accept_threshold_filters_pits(multi_severity_result: ReviewResult) -> None:
    """Acceptance: severity_threshold='major' matches golden snapshot."""
    output = render_comment(multi_severity_result, severity_threshold="major")
    expected = (FIXTURES_DIR / "golden_ripe_threshold_major.md").read_text(encoding="utf-8")
    assert output == expected


def test_default_threshold_unchanged(ripe_result_fixture: ReviewResult) -> None:
    """Sanity: default threshold 'info' matches existing golden ripe snapshot."""
    output = render_comment(ripe_result_fixture, severity_threshold="info")
    expected = (FIXTURES_DIR / "golden_ripe.md").read_text(encoding="utf-8")
    assert output == expected


# ---------------------------------------------------------------------------
# UI golden snapshot tests — cost footer
# ---------------------------------------------------------------------------


def test_ui_comment_with_cost_footer(ripe_result_fixture: ReviewResult) -> None:
    """Golden snapshot of a rendered comment with cost footer enabled."""
    from lychee.cost import compute_cost, format_cost_line

    cost_usd = compute_cost(ripe_result_fixture.usage, ripe_result_fixture.model)
    cost_line = format_cost_line(cost_usd, ripe_result_fixture.usage)
    output = render_comment(ripe_result_fixture, cost_line=cost_line)
    expected = (FIXTURES_DIR / "golden_ripe_cost_footer.md").read_text(encoding="utf-8")
    assert output == expected


def test_ui_comment_without_cost_footer(ripe_result_fixture: ReviewResult) -> None:
    """Golden snapshot without cost footer (cost_line=None)."""
    output = render_comment(ripe_result_fixture, cost_line=None)
    expected = (FIXTURES_DIR / "golden_ripe.md").read_text(encoding="utf-8")
    assert output == expected


# ---------------------------------------------------------------------------
# Fallback findings tests
# ---------------------------------------------------------------------------


@pytest.fixture
def fallback_findings() -> list[Finding]:
    """Two findings to use as fallback findings."""
    return [
        Finding(
            file="src/config.py",
            line=None,
            severity=Severity.info,
            category=Category.docs,
            message="Consider adding a module docstring.",
        ),
        Finding(
            file="src/other.py",
            line=99,
            severity=Severity.minor,
            category=Category.style,
            message="Line too long.",
        ),
    ]


def test_fallback_none_produces_unchanged_output(ripe_result_fixture: ReviewResult) -> None:
    """fallback_findings=None produces the same output as the default."""
    baseline = render_comment(ripe_result_fixture)
    with_none = render_comment(ripe_result_fixture, fallback_findings=None)
    assert baseline == with_none


def test_fallback_empty_produces_unchanged_output(ripe_result_fixture: ReviewResult) -> None:
    """fallback_findings=[] produces the same output as the default."""
    baseline = render_comment(ripe_result_fixture)
    with_empty = render_comment(ripe_result_fixture, fallback_findings=[])
    assert baseline == with_empty


def test_fallback_renders_details_block(
    ripe_result_fixture: ReviewResult,
    fallback_findings: list[Finding],
) -> None:
    """Non-empty fallback renders a <details> block."""
    output = render_comment(ripe_result_fixture, fallback_findings=fallback_findings)
    assert "<details>" in output
    assert "</details>" in output


def test_fallback_finding_messages_present(
    ripe_result_fixture: ReviewResult,
    fallback_findings: list[Finding],
) -> None:
    """Fallback finding messages appear in the output."""
    output = render_comment(ripe_result_fixture, fallback_findings=fallback_findings)
    for finding in fallback_findings:
        assert finding.message in output


def test_fallback_count_in_summary(
    ripe_result_fixture: ReviewResult,
    fallback_findings: list[Finding],
) -> None:
    """Fallback count appears in the summary text."""
    output = render_comment(ripe_result_fixture, fallback_findings=fallback_findings)
    assert "2 findings not posted inline" in output


def test_fallback_placement_after_pits_before_footer(
    ripe_result_fixture: ReviewResult,
    fallback_findings: list[Finding],
) -> None:
    """Fallback section appears after Pits and before the footer."""
    output = render_comment(ripe_result_fixture, fallback_findings=fallback_findings)
    pits_pos = output.index("## 🪨 Pits")
    details_pos = output.index("<details>")
    footer_pos = output.index("*Reviewed to the core by Lychee*")
    assert pits_pos < details_pos < footer_pos


def test_fallback_with_cost_line(
    ripe_result_fixture: ReviewResult,
    fallback_findings: list[Finding],
) -> None:
    """Integration: fallback + cost_line both render correctly."""
    cost = "💰 Cost: $0.003"
    output = render_comment(
        ripe_result_fixture, cost_line=cost, fallback_findings=fallback_findings
    )
    assert "<details>" in output
    assert cost in output
    # Order: details before cost before footer
    details_pos = output.index("<details>")
    cost_pos = output.index(cost)
    footer_pos = output.index("*Reviewed to the core by Lychee*")
    assert details_pos < cost_pos < footer_pos


def test_fallback_golden_snapshot(
    ripe_result_fixture: ReviewResult,
    fallback_findings: list[Finding],
) -> None:
    """Regression: fallback output matches golden snapshot exactly."""
    expected = (FIXTURES_DIR / "golden_ripe_with_fallback.md").read_text(encoding="utf-8")
    output = render_comment(ripe_result_fixture, fallback_findings=fallback_findings)
    assert output == expected


def test_fallback_single_finding(ripe_result_fixture: ReviewResult) -> None:
    """Single fallback finding uses singular 'finding' label."""
    fallback = [
        Finding(
            file="x.py",
            severity=Severity.info,
            category=Category.other,
            message="Note.",
        ),
    ]
    output = render_comment(ripe_result_fixture, fallback_findings=fallback)
    assert "1 finding not posted inline" in output


# ---------------------------------------------------------------------------
# severity_at_or_above tests
# ---------------------------------------------------------------------------


def test_severity_at_or_above_same() -> None:
    """Same severity is at or above itself."""
    assert severity_at_or_above("info", "info") is True
    assert severity_at_or_above("critical", "critical") is True


def test_severity_at_or_above_higher() -> None:
    """Higher severity is at or above a lower threshold."""
    assert severity_at_or_above("critical", "info") is True
    assert severity_at_or_above("major", "minor") is True


def test_severity_at_or_above_lower() -> None:
    """Lower severity is NOT at or above a higher threshold."""
    assert severity_at_or_above("info", "minor") is False
    assert severity_at_or_above("minor", "major") is False


def test_severity_at_or_above_all_pairs() -> None:
    """Exhaustive check of all severity pairs."""
    severities = ["info", "minor", "major", "critical"]
    for i, sev in enumerate(severities):
        for j, thresh in enumerate(severities):
            assert severity_at_or_above(sev, thresh) == (i >= j)
