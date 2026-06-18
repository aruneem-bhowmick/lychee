"""Diff-to-position mapping for GitHub inline review comments.

Parses unified diffs and maps ``(file, line)`` pairs to GitHub diff positions.
Position numbering follows GitHub's convention: the first line after a file's
first ``@@`` hunk header is position 1; every subsequent line (content and later
``@@`` headers) increments the position counter.  Only added (``+``) and
context (`` ``) lines are recorded as mappable — removed (``-``) lines do not
exist in the head revision and cannot receive inline comments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Regex matching a unified-diff file boundary.
_DIFF_HEADER_RE = re.compile(r"^diff --git a/.+ b/(.+)$")

# Regex matching the new-side (+++) file path header.
_PLUS_HEADER_RE = re.compile(r"^\+\+\+ (.+)$")

# Regex matching a hunk header, capturing the new-side start line number.
_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass(frozen=True)
class DiffPosition:
    """A resolved position in a unified diff.

    Attributes:
        path: File path as it appears in the diff (new side, ``b/`` stripped).
        position: 1-based line index within the diff for the file's section.
        head_line: The head-version line number this position corresponds to.
    """

    path: str
    position: int
    head_line: int


def build_position_map(diff: str) -> dict[str, dict[int, DiffPosition]]:
    """Parse a unified diff and build a map from file+head_line to DiffPosition.

    Returns:
        ``{file_path: {head_line_number: DiffPosition, ...}, ...}``

    Only lines that appear on the new (head) side of the diff are included:
    added lines (``+``) and context lines (`` ``).  Removed lines (``-``) are
    not mappable because they don't exist in the head version.

    File paths are normalized to the new-side path (from the ``+++`` header),
    with the leading ``b/`` prefix stripped.
    """
    position_map: dict[str, dict[int, DiffPosition]] = {}

    current_file: str | None = None
    position = 0
    head_line = 0
    first_hunk_seen = False

    for raw_line in diff.splitlines():
        # --- File boundary via "diff --git" header ---
        if _DIFF_HEADER_RE.match(raw_line):
            current_file = None
            position = 0
            head_line = 0
            first_hunk_seen = False
            continue

        # --- Before the file path is resolved, look for +++ header ---
        if current_file is None and not first_hunk_seen:
            plus_match = _PLUS_HEADER_RE.match(raw_line)
            if plus_match:
                path = plus_match.group(1)
                if path == "/dev/null":
                    # Deleted file — no head-side lines to map.
                    continue
                if path.startswith("b/"):
                    path = path[2:]
                current_file = path
                position_map.setdefault(current_file, {})
            continue

        if current_file is None:
            continue

        # --- Skip binary-file markers ---
        if raw_line.startswith("Binary files "):
            continue

        # --- Skip "\ No newline at end of file" markers ---
        if raw_line.startswith("\\ "):
            continue

        # --- Hunk header ---
        hunk_match = _HUNK_HEADER_RE.match(raw_line)
        if hunk_match:
            head_line = int(hunk_match.group(1))
            if not first_hunk_seen:
                # First hunk header — set position to 0 (not counted).
                position = 0
                first_hunk_seen = True
            else:
                # Subsequent hunk headers increment the position counter.
                position += 1
            continue

        # Skip metadata lines before the first hunk.
        if not first_hunk_seen:
            continue

        position += 1

        if raw_line.startswith("+"):
            position_map[current_file][head_line] = DiffPosition(
                path=current_file,
                position=position,
                head_line=head_line,
            )
            head_line += 1
        elif raw_line.startswith("-"):
            # Removed lines — not mappable; do not advance head_line.
            pass
        else:
            # Context line (starts with " " or is empty in some diffs).
            position_map[current_file][head_line] = DiffPosition(
                path=current_file,
                position=position,
                head_line=head_line,
            )
            head_line += 1

    return position_map


def map_finding_to_position(
    file: str,
    line: int | None,
    position_map: dict[str, dict[int, DiffPosition]],
) -> DiffPosition | None:
    """Map a Finding's file+line to a DiffPosition, or None if unmappable.

    Returns None when:
    - *line* is ``None`` (the Finding has no line reference)
    - *file* is not in the diff
    - *line* is not in any hunk of the file's diff
    """
    if line is None:
        return None

    file_map = position_map.get(file)
    if file_map is None:
        return None

    return file_map.get(line)


def parse_diff_files(diff: str) -> list[str]:
    """Extract the list of file paths (new side) present in the diff.

    Utility for callers that need the file list without the full position map.
    Returns file paths in the order they appear, with ``b/`` prefix stripped.
    Deleted files (``+++ /dev/null``) are excluded.
    """
    files: list[str] = []
    in_diff_block = False
    for raw_line in diff.splitlines():
        if _DIFF_HEADER_RE.match(raw_line):
            in_diff_block = True
            continue
        if in_diff_block:
            plus_match = _PLUS_HEADER_RE.match(raw_line)
            if plus_match:
                path = plus_match.group(1)
                if path != "/dev/null":
                    if path.startswith("b/"):
                        path = path[2:]
                    files.append(path)
                in_diff_block = False
            elif _HUNK_HEADER_RE.match(raw_line):
                # Reached a hunk without seeing +++ (shouldn't happen in valid diffs)
                in_diff_block = False
    return files
