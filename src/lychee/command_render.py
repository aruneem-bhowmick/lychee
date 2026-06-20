"""Per-command response renderers for @lychee commands.

Each renderer takes a ReviewResult and produces a markdown string suitable
for posting as a GitHub issue comment.  All renderers are pure functions
with no I/O dependencies.  The COMMAND_RENDERERS dict maps Command values
to their render functions for dispatch.
"""

from __future__ import annotations

from collections.abc import Callable

from lychee.commands import Command
from lychee.models import ReviewResult, Ripeness
from lychee.render import REVIEW_MARKER, render_comment

_RIPENESS_BADGE: dict[Ripeness, str] = {
    Ripeness.ripe: "🟢 **Ripe**",
    Ripeness.unripe: "🟡 **Unripe**",
    Ripeness.sour: "🔴 **Sour**",
}

_RIPENESS_VERDICT: dict[Ripeness, str] = {
    Ripeness.ripe: "this PR is ready to merge.",
    Ripeness.unripe: "this PR needs more work before merging.",
    Ripeness.sour: "this PR has critical issues that must be resolved.",
}

_SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "minor": 1,
    "major": 2,
    "critical": 3,
}


def _render_header() -> str:
    """Render the standard command response header with marker and title."""
    return f"{REVIEW_MARKER}\n🌴 Lychee peeled this PR"


def render_peel_response(
    result: ReviewResult,
    cost_line: str | None = None,
) -> str:
    """Render a full review response (same as render_comment).

    Delegates to render_comment() for the full summary format.
    Prefixed with the review marker.
    """
    return render_comment(result, cost_line=cost_line)


def render_juice_response(result: ReviewResult) -> str:
    """Render a Nectar-only response.

    Format: marker + header + Nectar section.
    """
    parts: list[str] = [
        _render_header(),
        "---",
        f"## 🍯 Nectar\n{result.summary}",
        "---",
        "*Reviewed to the core by Lychee*",
    ]
    return "\n\n".join(parts)


def render_pit_response(result: ReviewResult) -> str:
    """Render the core Pit (highest-severity finding) response.

    Selects the single highest-severity finding. If multiple findings
    share the highest severity, picks the first. If no findings exist,
    renders a "no pits found" message.

    Format: marker + header + single finding.
    """
    header = _render_header()

    if not result.findings:
        parts: list[str] = [
            header,
            "---",
            "## 🪨 Core Pit\n*No pits found. Clean PR!*",
            "---",
            "*Reviewed to the core by Lychee*",
        ]
        return "\n\n".join(parts)

    # Sort findings by severity rank (highest first), preserving order for ties.
    sorted_findings = sorted(
        result.findings,
        key=lambda f: _SEVERITY_RANK[f.severity.value],
        reverse=True,
    )
    top = sorted_findings[0]

    line_ref = f" (line {top.line})" if top.line is not None else ""
    category = top.category.value
    finding_text = f"- **[{category}]** `{top.file}`{line_ref}: {top.message}"
    if top.suggestion is not None:
        finding_text += f"\n\n  ```suggestion\n  {top.suggestion}\n  ```"

    severity_label = top.severity.value.title()
    parts = [
        header,
        "---",
        f"## 🪨 Core Pit\n### {severity_label}\n{finding_text}",
        "---",
        "*Reviewed to the core by Lychee*",
    ]
    return "\n\n".join(parts)


def render_ripe_response(result: ReviewResult) -> str:
    """Render a Ripeness-only response.

    Format: marker + header + ripeness badge + one-line verdict.
    """
    badge = _RIPENESS_BADGE[result.ripeness]
    verdict = _RIPENESS_VERDICT[result.ripeness]

    parts: list[str] = [
        _render_header(),
        f"**Ripeness:** {badge} — {verdict}",
        "*Reviewed to the core by Lychee*",
    ]
    return "\n\n".join(parts)


COMMAND_RENDERERS: dict[str, Callable[..., str]] = {
    Command.peel: render_peel_response,
    Command.juice: render_juice_response,
    Command.pit: render_pit_response,
    Command.ripe: render_ripe_response,
}
"""Maps Command values to their render functions."""
