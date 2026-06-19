"""Inline comment renderer — formats a single Finding for GitHub review comments."""

from __future__ import annotations

from lychee.models import Finding, Severity

SEVERITY_LABELS: dict[Severity, str] = {
    Severity.info: "Info",
    Severity.minor: "Minor",
    Severity.major: "Major",
    Severity.critical: "Critical",
}

_SEVERITY_EMOJI: dict[Severity, str] = {
    Severity.info: "ℹ️",  # noqa: RUF001
    Severity.minor: "⚠️",
    Severity.major: "🔶",
    Severity.critical: "🔴",
}


def render_inline_comment(finding: Finding) -> str:
    """Render a Finding as a GitHub inline review comment body.

    Format::

        {emoji} **[{Severity}]** (*{category}*): {message}

    The severity label is wrapped in bold brackets for visual weight, the
    category is rendered in italic parentheses for scannability, and an emoji
    prefix aids quick triage.  When the finding carries a suggestion, a GitHub
    suggestion block is appended so reviewers can apply the fix with one click.
    """
    emoji = _SEVERITY_EMOJI[finding.severity]
    label = SEVERITY_LABELS[finding.severity]
    category = finding.category.value
    body = f"{emoji} **[{label}]** (*{category}*): {finding.message}"

    if finding.suggestion is not None:
        body += "\n\n" + render_suggestion_block(finding.suggestion)

    return body


def render_suggestion_block(suggestion: str) -> str:
    """Wrap *suggestion* in GitHub's suggestion syntax for one-click apply.

    Trailing whitespace is stripped from each line and leading/trailing
    blank lines inside the fence are removed — GitHub renders them
    literally, which produces unwanted empty lines in the suggestion diff.

    Returns an empty string when *suggestion* is empty (defensive; Pydantic
    validation normally rejects empty suggestions).

    Returns::

        ```suggestion
        {suggestion}
        ```
    """
    if not suggestion:
        return ""

    # Strip trailing whitespace per line, then remove leading/trailing
    # blank lines inside the fence.
    lines = [line.rstrip() for line in suggestion.splitlines()]

    # Remove leading blank lines.
    while lines and not lines[0]:
        lines.pop(0)

    # Remove trailing blank lines.
    while lines and not lines[-1]:
        lines.pop()

    cleaned = "\n".join(lines)
    return f"```suggestion\n{cleaned}\n```"
