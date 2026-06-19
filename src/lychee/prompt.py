"""Prompt construction for the Anthropic Messages API.

Assembles the system prompt (persona, rubric, severity/ripeness definitions,
output instructions, optional conventions), the user message (PR metadata,
commits, diff, changed files), and the tool schema for ``submit_review``.

All functions are pure: deterministic for fixed inputs, no I/O, no side effects.
"""

from __future__ import annotations

from typing import Any

from lychee.config import LycheeConfig
from lychee.context import ReviewContext
from lychee.models import ReviewResult

_SECTION_SEP = "\n\n---\n\n"

_PERSONA = (
    'You are Lychee, an expert code reviewer. Your personality is "tough shell, sweet flesh":\n'
    "you are rigorous and thorough on code quality, but kind, constructive, and encouraging\n"
    "to the author. You never dismiss effort; you acknowledge what's done well before\n"
    "addressing what needs improvement."
)

_RUBRIC = """\
## Review Rubric

Evaluate the pull request across these categories:
- **correctness**: Logic errors, bugs, incorrect behavior
- **security**: Vulnerabilities, secret exposure, injection risks
- **performance**: Inefficiencies, unnecessary allocations, O(n²) where O(n) suffices
- **tests**: Missing coverage, flaky tests, inadequate assertions
- **style**: Naming, formatting, idiomatic patterns (only when impactful)
- **docs**: Missing or misleading documentation, outdated comments
- **other**: Anything else noteworthy"""

_SEVERITY = """\
## Severity Levels

- **critical**: Blocks merge. Security vulnerability, data loss, crash, or correctness bug \
that affects users.
- **major**: Should be fixed before merge. Significant quality, performance, or \
maintainability issue.
- **minor**: Nice to fix. Style, naming, minor inefficiency, or suggestion for improvement.
- **info**: Informational. Observation, praise, or context for the author. Does not require \
action."""

_RIPENESS = """\
## Ripeness (Merge-Readiness Verdict)

- **ripe**: Ready to merge. No critical or major findings. Minor/info findings are acceptable.
- **unripe**: Needs work. Has major findings that should be addressed before merge.
- **sour**: Do not merge. Has critical findings that must be resolved."""

_OUTPUT_INSTRUCTIONS = """\
## Output Instructions

You MUST call the `submit_review` tool with your complete review. Do not respond with
plain text. Your review must include:
- `ripeness`: Your merge-readiness verdict (ripe / unripe / sour).
- `summary`: A concise summary (the Nectar) of what this PR does and your overall assessment.
- `walkthrough`: A file-by-file walkthrough (the Peel) in markdown.
- `findings`: A list of specific findings (Pits), each with file, line, severity, category, \
message, and optional suggestion.

Be specific: reference exact file paths and line numbers. Provide actionable suggestions
where possible. If the PR is clean, say so — an empty findings list with ripeness "ripe" \
is valid."""


_TONE_INSTRUCTIONS: dict[str, str] = {
    "balanced": "",
    "concise": (
        "Be brief and concise throughout. "
        "Keep the Nectar (summary) under 3 sentences. "
        "Use a short bullet-list format for the walkthrough instead of full paragraphs. "
        "Keep each finding message to one sentence. "
        "Omit low-value details, minor style observations, and informational notes. "
        "Skip the walkthrough entirely if the PR is straightforward."
    ),
    "detailed": (
        "Be thorough and detailed throughout. "
        "Provide extensive context in the Nectar (summary), covering motivation and impact. "
        "Write a multi-paragraph walkthrough covering each changed file, explaining what "
        "changed and why it matters. "
        "Give verbose finding explanations with rationale and concrete examples of the "
        "problem and how to fix it. "
        "Include thorough suggestion blocks with complete, ready-to-apply code when possible."
    ),
}


def _conventions_section(conventions: str) -> str:
    """Format the optional project conventions section."""
    return (
        "## Project Conventions\n\n"
        "The following conventions apply to this codebase. Factor them into your review:\n\n"
        f"{conventions}"
    )


def build_system_prompt(
    config: LycheeConfig,
    conventions: str | None = None,
) -> str:
    """Build the system prompt with persona, rubric, and optional conventions.

    The system prompt contains:
    1. The reviewer persona.
    2. Severity definitions (info / minor / major / critical).
    3. Ripeness definitions (ripe / unripe / sour) with clear criteria.
    4. Category definitions (correctness / security / performance / tests / style / docs / other).
    5. Output expectations: the model MUST call submit_review with a complete ReviewResult.
    6. Conventions section (if conventions is not None and non-empty).

    The output is deterministic for a given config and conventions.
    """
    sections: list[str] = [
        _PERSONA,
        _RUBRIC,
        _SEVERITY,
        _RIPENESS,
        _OUTPUT_INSTRUCTIONS,
    ]

    if conventions:
        sections.append(_conventions_section(conventions))

    if config.review.tone != "balanced":
        sections.append(f"## Tone\n\n{_TONE_INSTRUCTIONS[config.review.tone]}")

    if config.review.language != "en":
        sections.append(
            f"## Language\n\nWrite your entire review "
            f"(summary, walkthrough, and finding messages) in {config.review.language}."
        )

    return _SECTION_SEP.join(sections)


def build_system_prompt_blocks(
    config: LycheeConfig,
    conventions: str | None = None,
) -> list[dict[str, Any]]:
    """Build the system prompt as a list of cacheable content blocks.

    Wraps the output of ``build_system_prompt()`` in an Anthropic content
    block with ``cache_control`` set to ``{"type": "ephemeral"}``.  This
    allows the SDK to serve cached reads on repeated or concurrent reviews,
    reducing input-token costs on cache hits.

    The returned structure is accepted directly by the ``system`` parameter
    of the Anthropic Messages API.
    """
    text = build_system_prompt(config, conventions=conventions)
    return [
        {
            "type": "text",
            "text": text,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def build_user_message(context: ReviewContext) -> str:
    """Build the user message containing the PR context for review.

    Includes:
    1. PR metadata: title, author, base/head refs, PR body.
    2. Commit messages.
    3. Unified diff.
    4. Changed file contents (with filenames as headers).

    The output is deterministic for a given ReviewContext.
    """
    pr_body = context.pr_body if context.pr_body is not None else ""

    sections: list[str] = []

    # PR metadata
    metadata = (
        f"## Pull Request: {context.pr_title}\n\n"
        f"Author: {context.pr_author}\n"
        f"Base: {context.base_ref} ← Head: {context.head_ref}\n\n"
        f"{pr_body}"
    )
    sections.append(metadata)

    # Commit messages
    if context.commit_messages:
        numbered = "\n".join(f"{i}. {msg}" for i, msg in enumerate(context.commit_messages, 1))
        sections.append(f"## Commit Messages\n\n{numbered}")
    else:
        sections.append("## Commit Messages\n\nNo commit messages available.")

    # Unified diff
    sections.append(f"## Unified Diff\n\n```diff\n{context.diff}\n```")

    # Changed files
    if context.changed_files:
        file_parts: list[str] = ["## Changed Files"]
        for f in context.changed_files:
            filename: str = f["filename"]
            content: str | None = f.get("content_at_head")
            if content is None:
                file_parts.append(f"### {filename}\n\n*Binary, deleted, or too large to display.*")
            else:
                ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
                file_parts.append(f"### {filename}\n\n```{ext}\n{content}\n```")
        sections.append("\n\n".join(file_parts))
    else:
        sections.append("## Changed Files\n\nNo changed files.")

    return "\n\n".join(sections)


def build_map_user_message(
    context: ReviewContext,
    file_group: list[dict[str, Any]],
    group_index: int,
    total_groups: int,
) -> str:
    """Build a user message scoped to a single file group for the map phase.

    Creates a shallow copy of *context* with ``changed_files`` and ``diff``
    narrowed to only the files in *file_group*, prepends a group header, then
    delegates to ``build_user_message()``.  The original context is not mutated.
    """
    from lychee.review import _filter_diff_for_files

    filenames = {f["filename"] for f in file_group}
    filtered_diff = _filter_diff_for_files(context.diff, filenames)

    scoped_context = context.model_copy(update={"changed_files": file_group, "diff": filtered_diff})

    header = (
        f"## Review Group {group_index + 1} of {total_groups}\n\n"
        f"This is a partial review of a large PR. "
        f"You are reviewing files {group_index * len(file_group) + 1}"
        f"-{group_index * len(file_group) + len(file_group)} "
        f"of {sum(1 for _ in range(total_groups)) * len(file_group)} total files "
        f"(approximate).\n"
        f"Focus your review on only the files shown below."
    )

    return header + "\n\n" + build_user_message(scoped_context)


def build_reduce_user_message(
    context: ReviewContext,
    partial_results: list[dict[str, Any]],
) -> str:
    """Build a user message for the reduce phase that merges partial map results.

    Includes PR metadata, all partial summaries/walkthroughs/findings, and
    merge instructions directing the model to produce a single coherent
    ReviewResult.
    """
    pr_body = context.pr_body if context.pr_body is not None else ""

    sections: list[str] = []

    # PR metadata (condensed)
    sections.append(
        f"## Pull Request: {context.pr_title}\n\n"
        f"Author: {context.pr_author}\n"
        f"Base: {context.base_ref} ← Head: {context.head_ref}\n\n"
        f"{pr_body}"
    )

    # Merge instructions
    sections.append(
        "## Merge Instructions\n\n"
        "You are performing the **reduce** step of a map-reduce review.\n"
        "Below are the partial review results from reviewing this PR in groups.\n"
        "Your job is to merge them into a single, coherent review:\n\n"
        "1. **Ripeness**: Choose the most conservative verdict across all partials "
        "(sour > unripe > ripe).\n"
        "2. **Summary**: Write a unified summary covering the entire PR.\n"
        "3. **Walkthrough**: Combine all file walkthroughs into one ordered walkthrough.\n"
        "4. **Findings**: Include all findings from all partials. De-duplicate exact "
        "duplicates but keep all distinct findings.\n"
    )

    # Partial results
    for i, partial in enumerate(partial_results, 1):
        sections.append(
            f"## Partial Review {i} of {len(partial_results)}\n\n"
            f"### Summary\n{partial['summary']}\n\n"
            f"### Walkthrough\n{partial['walkthrough']}\n\n"
            f"### Ripeness\n{partial['ripeness']}\n\n"
            f"### Findings\n"
            + "\n".join(
                f"- **{f['severity']}** ({f['category']}) `{f['file']}`"
                + (f":{f['line']}" if f.get("line") else "")
                + f": {f['message']}"
                for f in partial.get("findings", [])
            )
        )

    return "\n\n".join(sections)


def build_messages(
    context: ReviewContext,
    config: LycheeConfig,
) -> list[dict[str, Any]]:
    """Construct the Anthropic Messages API message list for a PR review.

    Returns a list with a single user message dict:
    ``[{"role": "user", "content": <user_message>}]``

    The system prompt is returned separately via ``build_system_prompt()``
    and passed to the Claude client as the ``system`` parameter.
    """
    return [{"role": "user", "content": build_user_message(context)}]


def get_tools() -> list[dict[str, Any]]:
    """Return the tools list for the Messages API call.

    Returns ``[ReviewResult.to_tool_schema()]``.
    """
    return [ReviewResult.to_tool_schema()]
