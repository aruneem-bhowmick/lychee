"""Tests for per-command response renderers (command_render.py).

Covers unit tests for each renderer, parametrized edge cases, snapshot
regression tests, and the COMMAND_RENDERERS mapping.

Framework: pytest, ReviewResult fixtures from conftest.py.
"""
# P4-R2

from __future__ import annotations

import pytest

from lychee.command_render import (
    COMMAND_RENDERERS,
    render_juice_response,
    render_peel_response,
    render_pit_response,
    render_ripe_response,
)
from lychee.commands import Command
from lychee.models import (
    Category,
    Finding,
    ReviewResult,
    Ripeness,
    Severity,
)
from lychee.render import REVIEW_MARKER


def _make_result(
    *,
    ripeness: Ripeness = Ripeness.ripe,
    summary: str = "Test summary.",
    walkthrough: str = "## Test\n\nNo changes.",
    findings: list[Finding] | None = None,
    model: str = "claude-sonnet-4-6",
) -> ReviewResult:
    """Build a ReviewResult for testing."""
    if findings is None:
        findings = [
            Finding(
                file="test.py",
                line=10,
                severity=Severity.minor,
                category=Category.style,
                message="Consider renaming.",
            ),
        ]
    return ReviewResult(
        ripeness=ripeness,
        summary=summary,
        walkthrough=walkthrough,
        findings=findings,
        model=model,
        usage={"input_tokens": 100, "output_tokens": 50},
    )


def _make_multi_severity_result() -> ReviewResult:
    """Build a ReviewResult with findings of varying severity."""
    return _make_result(
        ripeness=Ripeness.sour,
        findings=[
            Finding(
                file="low.py",
                line=1,
                severity=Severity.info,
                category=Category.docs,
                message="Info finding.",
            ),
            Finding(
                file="mid.py",
                line=5,
                severity=Severity.minor,
                category=Category.style,
                message="Minor finding.",
            ),
            Finding(
                file="high.py",
                line=10,
                severity=Severity.critical,
                category=Category.correctness,
                message="Critical finding.",
            ),
            Finding(
                file="also_high.py",
                line=20,
                severity=Severity.critical,
                category=Category.security,
                message="Another critical finding.",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_command_render_module_imports() -> None:  # P4-R2
    """All public names can be imported from command_render."""
    from lychee.command_render import (
        COMMAND_RENDERERS,
        render_juice_response,
        render_peel_response,
        render_pit_response,
        render_ripe_response,
    )

    assert callable(render_peel_response)
    assert callable(render_juice_response)
    assert callable(render_pit_response)
    assert callable(render_ripe_response)
    assert isinstance(COMMAND_RENDERERS, dict)


# ---------------------------------------------------------------------------
# Unit tests — render_peel_response
# ---------------------------------------------------------------------------


class TestRenderPeelResponse:
    """Unit tests for render_peel_response."""

    def test_render_peel_full_output(self) -> None:  # P4-R2
        """render_peel_response produces the full summary format."""
        result = _make_result()
        output = render_peel_response(result)

        assert REVIEW_MARKER in output
        assert "Nectar" in output
        assert "The Peel" in output
        assert "Pits" in output
        assert result.summary in output
        assert result.walkthrough in output

    def test_render_peel_with_cost_line(self) -> None:  # P4-R2
        """render_peel_response includes cost line when provided."""
        result = _make_result()
        output = render_peel_response(result, cost_line="**Cost:** $0.0010")
        assert "**Cost:** $0.0010" in output

    def test_render_peel_without_cost_line(self) -> None:  # P4-R2
        """render_peel_response omits cost line when None."""
        result = _make_result()
        output = render_peel_response(result, cost_line=None)
        assert "**Cost:**" not in output


# ---------------------------------------------------------------------------
# Unit tests — render_juice_response
# ---------------------------------------------------------------------------


class TestRenderJuiceResponse:
    """Unit tests for render_juice_response."""

    def test_render_juice_nectar_only(self) -> None:  # P4-R2
        """render_juice_response includes Nectar, excludes walkthrough and findings."""
        result = _make_result()
        output = render_juice_response(result)

        assert "Nectar" in output
        assert result.summary in output
        assert "The Peel" not in output
        assert "Pits" not in output

    def test_render_juice_no_walkthrough(self) -> None:  # P4-R2
        """render_juice_response does not contain the walkthrough text."""
        result = _make_result(walkthrough="## Detailed walkthrough content")
        output = render_juice_response(result)
        assert "Detailed walkthrough content" not in output

    def test_render_juice_no_findings(self) -> None:  # P4-R2
        """render_juice_response does not list individual findings."""
        result = _make_result()
        output = render_juice_response(result)
        assert "test.py" not in output


# ---------------------------------------------------------------------------
# Unit tests — render_pit_response
# ---------------------------------------------------------------------------


class TestRenderPitResponse:
    """Unit tests for render_pit_response."""

    def test_render_pit_highest_severity(self) -> None:  # P4-R2
        """render_pit_response selects the critical finding over minor ones."""
        result = _make_multi_severity_result()
        output = render_pit_response(result)

        assert "Critical" in output
        assert "Critical finding." in output
        assert "high.py" in output

    def test_render_pit_no_findings(self) -> None:  # P4-R2
        """render_pit_response with empty findings produces 'no pits' message."""
        result = _make_result(findings=[])
        output = render_pit_response(result)

        assert "No pits found" in output
        assert "Clean PR" in output

    def test_render_pit_tie_breaking(self) -> None:  # P4-R2
        """When multiple findings share the highest severity, the first is selected."""
        result = _make_multi_severity_result()
        output = render_pit_response(result)

        # The first critical finding should be selected (high.py, line 10).
        assert "high.py" in output
        assert "Critical finding." in output
        # The second critical finding should NOT be in the output.
        assert "also_high.py" not in output

    def test_render_pit_single_finding(self) -> None:  # P4-R2
        """render_pit_response with a single finding renders that finding."""
        result = _make_result(
            findings=[
                Finding(
                    file="only.py",
                    line=42,
                    severity=Severity.major,
                    category=Category.performance,
                    message="Slow query.",
                ),
            ],
        )
        output = render_pit_response(result)

        assert "only.py" in output
        assert "Slow query." in output
        assert "Major" in output

    def test_render_pit_with_suggestion(self) -> None:  # P4-R2
        """render_pit_response includes suggestion block when present."""
        result = _make_result(
            findings=[
                Finding(
                    file="fix.py",
                    line=1,
                    severity=Severity.critical,
                    category=Category.correctness,
                    message="Bug here.",
                    suggestion="fixed_code()",
                ),
            ],
        )
        output = render_pit_response(result)
        assert "```suggestion" in output
        assert "fixed_code()" in output


# ---------------------------------------------------------------------------
# Unit tests — render_ripe_response
# ---------------------------------------------------------------------------


class TestRenderRipeResponse:
    """Unit tests for render_ripe_response."""

    def test_render_ripe_verdict(self) -> None:  # P4-R2
        """render_ripe_response includes ripeness badge and one-line verdict."""
        result = _make_result(ripeness=Ripeness.ripe)
        output = render_ripe_response(result)

        assert "Ripeness:" in output
        assert "Ripe" in output
        assert "ready to merge" in output

    @pytest.mark.parametrize(
        ("ripeness", "badge_fragment", "verdict_fragment"),
        [
            pytest.param(Ripeness.ripe, "Ripe", "ready to merge", id="ripe"),
            pytest.param(Ripeness.unripe, "Unripe", "needs more work", id="unripe"),
            pytest.param(Ripeness.sour, "Sour", "critical issues", id="sour"),
        ],
    )
    def test_render_ripe_each_ripeness(  # P4-R2
        self,
        ripeness: Ripeness,
        badge_fragment: str,
        verdict_fragment: str,
    ) -> None:
        """Parametrize over ripe, unripe, sour; verify each badge."""
        result = _make_result(ripeness=ripeness)
        output = render_ripe_response(result)

        assert badge_fragment in output
        assert verdict_fragment in output

    def test_render_ripe_no_findings_listed(self) -> None:  # P4-R2
        """render_ripe_response does not include individual findings."""
        result = _make_multi_severity_result()
        output = render_ripe_response(result)

        assert "high.py" not in output
        assert "low.py" not in output


# ---------------------------------------------------------------------------
# Unit tests — COMMAND_RENDERERS dict
# ---------------------------------------------------------------------------


class TestCommandRenderersDict:
    """Tests for the COMMAND_RENDERERS mapping."""

    def test_command_renderers_dict(self) -> None:  # P4-R2
        """COMMAND_RENDERERS maps all four command values."""
        assert set(COMMAND_RENDERERS.keys()) == {
            Command.peel.value,
            Command.juice.value,
            Command.pit.value,
            Command.ripe.value,
        }

    def test_command_renderers_are_callable(self) -> None:  # P4-R2
        """Every value in COMMAND_RENDERERS is callable."""
        for name, renderer in COMMAND_RENDERERS.items():
            assert callable(renderer), f"Renderer for {name} is not callable"


# ---------------------------------------------------------------------------
# Marker tests
# ---------------------------------------------------------------------------


class TestAllRenderersIncludeMarker:
    """Verify every renderer's output includes REVIEW_MARKER."""

    def test_all_renderers_include_marker(self) -> None:  # P4-R2
        """Every renderer's output includes REVIEW_MARKER."""
        result = _make_result()

        assert REVIEW_MARKER in render_peel_response(result)
        assert REVIEW_MARKER in render_juice_response(result)
        assert REVIEW_MARKER in render_pit_response(result)
        assert REVIEW_MARKER in render_ripe_response(result)

    def test_marker_in_empty_findings_pit(self) -> None:  # P4-R2
        """Pit renderer with no findings still includes the marker."""
        result = _make_result(findings=[])
        assert REVIEW_MARKER in render_pit_response(result)


# ---------------------------------------------------------------------------
# Regression / snapshot tests
# ---------------------------------------------------------------------------


class TestRenderSnapshots:
    """Golden snapshot tests for command responses."""

    def _fixed_result(self) -> ReviewResult:
        """Build a deterministic ReviewResult for snapshot comparison."""
        return ReviewResult(
            ripeness=Ripeness.unripe,
            summary="Two issues found in the utils module.",
            walkthrough="## Changes\n\nAdded helper functions in `src/utils.py`.",
            findings=[
                Finding(
                    file="src/utils.py",
                    line=5,
                    severity=Severity.major,
                    category=Category.correctness,
                    message="Possible null dereference.",
                    suggestion="if x is not None:\n    return x",
                ),
                Finding(
                    file="src/utils.py",
                    line=12,
                    severity=Severity.minor,
                    category=Category.style,
                    message="Function name could be more descriptive.",
                ),
            ],
            model="claude-sonnet-4-6",
            usage={"input_tokens": 800, "output_tokens": 200},
        )

    def test_peel_response_snapshot(self) -> None:  # P4-R2
        """Golden snapshot of the full peel response for a fixed ReviewResult."""
        result = self._fixed_result()
        output = render_peel_response(result)

        # Verify structural markers.
        assert REVIEW_MARKER in output
        assert "Nectar" in output
        assert "The Peel" in output
        assert "Pits" in output
        assert "Two issues found" in output
        assert "Possible null dereference" in output

    def test_juice_response_snapshot(self) -> None:  # P4-R2
        """Golden snapshot of the juice response."""
        result = self._fixed_result()
        output = render_juice_response(result)

        assert REVIEW_MARKER in output
        assert "Nectar" in output
        assert "Two issues found" in output
        assert "The Peel" not in output
        assert "Pits" not in output

    def test_pit_response_snapshot(self) -> None:  # P4-R2
        """Golden snapshot of the pit response."""
        result = self._fixed_result()
        output = render_pit_response(result)

        assert REVIEW_MARKER in output
        assert "Core Pit" in output
        assert "Major" in output
        assert "Possible null dereference." in output
        assert "src/utils.py" in output
        # Only the top finding should appear.
        assert "Function name could be more descriptive" not in output

    @pytest.mark.parametrize(
        "ripeness",
        [Ripeness.ripe, Ripeness.unripe, Ripeness.sour],
        ids=["ripe", "unripe", "sour"],
    )
    def test_ripe_response_snapshot(self, ripeness: Ripeness) -> None:  # P4-R2
        """Golden snapshot of the ripe response (for each ripeness value)."""
        result = _make_result(ripeness=ripeness)
        output = render_ripe_response(result)

        assert REVIEW_MARKER in output
        assert "Ripeness:" in output
        assert "Lychee peeled this PR" in output


# ---------------------------------------------------------------------------
# UI format tests
# ---------------------------------------------------------------------------


class TestUIFormat:
    """UI tests verifying the rendered format of each response."""

    def test_ui_peel_response_format(self) -> None:  # P4-R2
        """Peel response matches the full summary comment format."""
        result = _make_result()
        output = render_peel_response(result)

        assert output.startswith(REVIEW_MARKER)
        assert "Lychee peeled this PR" in output
        assert "Nectar" in output
        assert "The Peel" in output
        assert "Pits" in output
        assert "Reviewed to the core by Lychee" in output

    def test_ui_juice_response_format(self) -> None:  # P4-R2
        """Juice response has header + nectar only."""
        result = _make_result()
        output = render_juice_response(result)

        assert output.startswith(REVIEW_MARKER)
        assert "Nectar" in output
        assert "Reviewed to the core by Lychee" in output
        assert "The Peel" not in output
        assert "Pits" not in output

    def test_ui_pit_response_format(self) -> None:  # P4-R2
        """Pit response has header + single finding."""
        result = _make_result()
        output = render_pit_response(result)

        assert output.startswith(REVIEW_MARKER)
        assert "Core Pit" in output
        assert "Reviewed to the core by Lychee" in output

    def test_ui_ripe_response_format(self) -> None:  # P4-R2
        """Ripe response has header + ripeness badge."""
        result = _make_result()
        output = render_ripe_response(result)

        assert output.startswith(REVIEW_MARKER)
        assert "Ripeness:" in output
        assert "Reviewed to the core by Lychee" in output
