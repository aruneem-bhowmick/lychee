"""Diff-to-position mapping for GitHub inline review comments.

Parses unified diffs and maps ``(file, line)`` pairs to GitHub diff positions.
Position numbering follows GitHub's convention: the first line after a ``@@``
header in a file's diff is position 1; every subsequent line (content and later
``@@`` headers) increments the position counter.  Only added (``+``) and
context (`` ``) lines are recorded as mappable — removed (``-``) lines do not
exist in the head revision and cannot receive inline comments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lychee.models import Finding

# Regex matching a unified-diff file header.
_DIFF_HEADER_RE = re.compile(r"^diff --git a/.+ b/(.+)$")

# Regex matching a hunk header, capturing the new-side start line number.
_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass(frozen=True)
class DiffPosition:
    """A resolved inline-comment position within a GitHub diff.

    Attributes:
        path: The file path as it appears in the diff (``b/`` prefix stripped).
        position: The 1-based position within the diff hunk (GitHub's numbering).
        line: The 1-based line number on the head (new) side of the file.
    """

    path: str
    position: int
    line: int


def build_position_map(diff: str) -> dict[str, dict[int, int]]:
    """Walk a unified diff and build a ``{file: {line: position}}`` mapping.

    Only added (``+``) and context (`` ``) lines are recorded — these
    correspond to lines present in the head revision that can receive
    inline comments.

    Returns an empty dict when *diff* is empty.
    """
    position_map: dict[str, dict[int, int]] = {}

    current_file: str | None = None
    position = 0  # 1-based position within the current file's diff
    head_line = 0  # current line number on the new (head) side

    for raw_line in diff.splitlines():
        # New file header — reset per-file counters.
        file_match = _DIFF_HEADER_RE.match(raw_line)
        if file_match:
            current_file = file_match.group(1)
            position_map.setdefault(current_file, {})
            position = 0
            head_line = 0
            continue

        if current_file is None:
            continue

        # Hunk header — reset head-line counter, advance position.
        hunk_match = _HUNK_HEADER_RE.match(raw_line)
        if hunk_match:
            head_line = int(hunk_match.group(1))
            position += 1
            continue

        # Skip metadata lines (index, ---, +++) before the first hunk.
        if position == 0:
            continue

        position += 1

        if raw_line.startswith("+"):
            position_map[current_file][head_line] = position
            head_line += 1
        elif raw_line.startswith("-"):
            # Removed lines — not mappable, don't advance head_line.
            pass
        else:
            # Context line (starts with " " or is empty in some diffs).
            position_map[current_file][head_line] = position
            head_line += 1

    return position_map


def map_finding_to_position(
    finding: Finding,
    position_map: dict[str, dict[int, int]],
) -> DiffPosition | None:
    """Map a Finding's file+line to a ``DiffPosition``, or ``None`` if unmappable.

    A finding is unmappable when:
    - Its ``line`` is ``None`` (file-level finding).
    - Its file is not present in the diff.
    - Its line is not in the set of added/context lines.
    """
    if finding.line is None:
        return None

    file_map = position_map.get(finding.file)
    if file_map is None:
        return None

    position = file_map.get(finding.line)
    if position is None:
        return None

    return DiffPosition(path=finding.file, position=position, line=finding.line)


def parse_diff_files(diff: str) -> list[str]:
    """Extract the list of file paths from a unified diff.

    Returns file paths in the order they appear in the diff.
    """
    files: list[str] = []
    for line in diff.splitlines():
        m = _DIFF_HEADER_RE.match(line)
        if m:
            files.append(m.group(1))
    return files
