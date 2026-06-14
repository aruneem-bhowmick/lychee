"""Comment renderer — converts a ReviewResult to GitHub PR markdown."""

from __future__ import annotations

from lychee.models import Finding, ReviewResult, Ripeness, Severity

REVIEW_MARKER = "<!-- lychee:review -->"

_SEVERITY_ORDER: list[Severity] = [
    Severity.critical,
    Severity.major,
    Severity.minor,
    Severity.info,
]

_SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "minor": 1,
    "major": 2,
    "critical": 3,
}

_RIPENESS_BADGE: dict[Ripeness, str] = {
    Ripeness.ripe: "🟢 **Ripe**",
    Ripeness.unripe: "🟡 **Unripe**",
    Ripeness.sour: "🔴 **Sour**",
}


def render_comment(
    result: ReviewResult,
    cost_line: str | None = None,
    severity_threshold: str = "info",
) -> str:
    """Render a ReviewResult to the PR comment markdown string.

    Sections in order: Header → Nectar → The Peel → Pits → Footer.
    cost_line is inserted before the footer when provided; pass None to omit it entirely.
    severity_threshold filters out findings below the given severity level.
    """
    threshold_rank = _SEVERITY_RANK[severity_threshold]
    filtered = [f for f in result.findings if _SEVERITY_RANK[f.severity.value] >= threshold_rank]

    parts: list[str] = [
        _render_header(result),
        "---",
        f"## 🍯 Nectar\n{result.summary}",
        "---",
        f"## 🌿 The Peel\n{result.walkthrough}",
        "---",
        f"## 🪨 Pits\n{_render_pits(filtered)}",
        "---",
    ]
    if cost_line is not None:
        parts.append(cost_line)
    parts.append("*Reviewed to the core by Lychee*")
    return "\n\n".join(parts)


def _render_header(result: ReviewResult) -> str:
    """Render the Header block: hidden marker, title, model name, and Ripeness badge."""
    badge = _RIPENESS_BADGE[result.ripeness]
    return f"{REVIEW_MARKER}\n🌴 Lychee peeled this PR\n\n**Model:** {result.model} | {badge}"


def _render_pits(findings: list[Finding]) -> str:
    """Render all Pits grouped by severity (critical → major → minor → info).

    Returns a clean-PR message when findings is empty; otherwise renders one
    headed group per non-empty severity level in severity order.
    """
    if not findings:
        return "*No pits found. Clean PR!*"

    groups: list[str] = []
    for severity in _SEVERITY_ORDER:
        group = [f for f in findings if f.severity == severity]
        if not group:
            continue
        heading = f"### {severity.value.title()} ({len(group)})"
        items = "\n".join(_render_finding(f) for f in group)
        groups.append(f"{heading}\n{items}")

    return "\n\n".join(groups)


def _render_finding(finding: Finding) -> str:
    """Render a single Finding as a markdown list item with optional suggestion block."""
    line_ref = f" (line {finding.line})" if finding.line is not None else ""
    category = finding.category.value
    base = f"- **[{category}]** `{finding.file}`{line_ref}: {finding.message}"

    if finding.suggestion is not None:
        suggestion_block = f"\n\n  ```suggestion\n  {finding.suggestion}\n  ```"
        return base + suggestion_block

    return base
