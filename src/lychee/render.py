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


def severity_at_or_above(severity: str, threshold: str) -> bool:
    """Return True if *severity* is at or above *threshold*.

    Both arguments must be valid severity strings (``info``, ``minor``,
    ``major``, ``critical``).  This is a public helper that exposes the
    severity comparison logic without leaking ``_SEVERITY_RANK``.
    """
    return _SEVERITY_RANK[severity] >= _SEVERITY_RANK[threshold]


def render_comment(
    result: ReviewResult,
    cost_line: str | None = None,
    severity_threshold: str = "info",
    fallback_findings: list[Finding] | None = None,
) -> str:
    """Render a ReviewResult to the PR comment markdown string.

    Sections in order:
        Header → Nectar → (Fallback) → The Peel → Pits → Footer.

    *cost_line* is inserted before the footer when provided; pass ``None``
    to omit it.

    *severity_threshold* filters findings in both the Pits section and the
    fallback section; findings below the threshold are excluded from both.

    *fallback_findings*, when non-empty, renders a
    ``### Findings not on changed lines`` section between the Nectar and
    The Peel.  Each finding is labeled ``(not on a changed line)`` so the
    author understands why it appears in the summary rather than inline.
    When ``None`` or empty, the section is omitted and output is identical
    to the no-fallback case.
    """
    threshold_rank = _SEVERITY_RANK[severity_threshold]
    filtered = [f for f in result.findings if _SEVERITY_RANK[f.severity.value] >= threshold_rank]

    parts: list[str] = [
        _render_header(result),
        "---",
        f"## 🍯 Nectar\n{result.summary}",
        "---",
    ]

    # Fallback findings sit between Nectar and The Peel so the author
    # sees them early, but they remain visually separated from the inline
    # findings reported in the Pits section.
    if fallback_findings:
        filtered_fallback = [
            f for f in fallback_findings if _SEVERITY_RANK[f.severity.value] >= threshold_rank
        ]
        if filtered_fallback:
            parts.append(_render_fallback_findings(filtered_fallback))
            parts.append("---")

    parts += [
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


def _render_fallback_findings(findings: list[Finding]) -> str:
    """Render unmappable findings under a ``### Findings not on changed lines`` heading.

    These are findings that could not be posted as inline review comments
    because their file/line does not appear in any diff hunk.  Each finding
    is labeled ``(not on a changed line)`` so the author understands why it
    is in the summary rather than inline.

    Suggestions are rendered in a plain code block (not a ``suggestion``
    block, since GitHub's one-click-apply only works on inline comments).
    """
    items = "\n".join(_render_fallback_finding(f) for f in findings)
    return f"### Findings not on changed lines\n{items}"


def _render_fallback_finding(finding: Finding) -> str:
    """Render a single unmappable Finding as a labeled markdown list item.

    Format::

        - **[severity]** ``file:line`` (*category*): message *(not on a changed line)*

    When *line* is ``None``, the location renders as ``file`` without a
    line number.  Suggestions are wrapped in a plain fenced code block.
    """
    severity = finding.severity.value
    location = (
        f"`{finding.file}:{finding.line}`" if finding.line is not None else f"`{finding.file}`"
    )
    category = finding.category.value
    base = (
        f"- **[{severity}]** {location} (*{category}*): "
        f"{finding.message} *(not on a changed line)*"
    )

    if finding.suggestion is not None:
        code_block = f"\n\n  ```\n  {finding.suggestion}\n  ```"
        return base + code_block

    return base
