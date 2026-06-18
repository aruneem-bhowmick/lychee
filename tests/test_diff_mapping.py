"""Unit, integration, acceptance, and regression tests for lychee.diff_mapping.

Covers build_position_map(), map_finding_to_position(), parse_diff_files(),
and the DiffPosition dataclass.  Tests use inline diff strings and the
shared diff_simple / diff_large fixtures from conftest.

Framework: pytest.  Coverage target: >= 90% on src/lychee/diff_mapping.py.
"""

from __future__ import annotations

import pytest

from lychee.diff_mapping import (
    DiffPosition,
    build_position_map,
    map_finding_to_position,
    parse_diff_files,
)
from lychee.models import Category, Finding, Severity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SINGLE_HUNK_DIFF = """\
diff --git a/src/app.py b/src/app.py
index aaa..bbb 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
 import os
+import sys

 def main():
"""

MULTI_HUNK_DIFF = """\
diff --git a/src/app.py b/src/app.py
index aaa..bbb 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
 import os
+import sys

 def main():
@@ -10,3 +11,4 @@
     pass

+# new comment
 x = 1
"""

NEW_FILE_DIFF = """\
diff --git a/src/new.py b/src/new.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/src/new.py
@@ -0,0 +1,3 @@
+line one
+line two
+line three
"""

DELETED_FILE_DIFF = """\
diff --git a/src/old.py b/src/old.py
deleted file mode 100644
index 1234567..0000000
--- a/src/old.py
+++ /dev/null
@@ -1,3 +0,0 @@
-line one
-line two
-line three
"""

REMOVED_LINES_DIFF = """\
diff --git a/src/app.py b/src/app.py
index aaa..bbb 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,5 +1,3 @@
 import os
-import sys
-import re
+import pathlib

 def main():
"""


def _make_finding(file: str = "src/app.py", line: int | None = 2, **kwargs: object) -> Finding:
    """Create a Finding with sensible defaults."""
    defaults: dict[str, object] = {
        "file": file,
        "line": line,
        "severity": Severity.minor,
        "category": Category.style,
        "message": "test finding",
    }
    defaults.update(kwargs)
    return Finding(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_imports() -> None:
    """All public names import cleanly from lychee.diff_mapping."""
    from lychee.diff_mapping import (
        DiffPosition,
        build_position_map,
        map_finding_to_position,
        parse_diff_files,
    )

    assert callable(build_position_map)
    assert callable(map_finding_to_position)
    assert callable(parse_diff_files)
    assert DiffPosition is not None


# ---------------------------------------------------------------------------
# Unit tests — build_position_map
# ---------------------------------------------------------------------------


def test_build_position_map_single_hunk() -> None:
    """Single hunk: added line and context lines are mapped."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    assert "src/app.py" in pmap
    file_map = pmap["src/app.py"]
    # Line 1 is context " import os" → position 2 (hunk header is pos 1)
    assert file_map[1] == 2
    # Line 2 is added "+import sys" → position 3
    assert file_map[2] == 3
    # Line 3 is context " " → position 4
    assert file_map[3] == 4
    # Line 4 is context " def main():" → position 5
    assert file_map[4] == 5


def test_build_position_map_multi_hunk() -> None:
    """Multi-hunk: positions continue incrementing across hunks."""
    pmap = build_position_map(MULTI_HUNK_DIFF)
    file_map = pmap["src/app.py"]
    # First hunk header is position 1; lines are 2-5.
    # Second hunk header is position 6.
    # "    pass" context → pos 7, head_line=11
    assert file_map[11] == 7
    # " " context → pos 8, head_line=12
    assert file_map[12] == 8
    # "+# new comment" added → pos 9, head_line=13
    assert file_map[13] == 9
    # " x = 1" context → pos 10, head_line=14
    assert file_map[14] == 10


def test_build_position_map_new_file() -> None:
    """New file: all added lines are mapped starting from position 2."""
    pmap = build_position_map(NEW_FILE_DIFF)
    file_map = pmap["src/new.py"]
    assert file_map[1] == 2  # +line one
    assert file_map[2] == 3  # +line two
    assert file_map[3] == 4  # +line three


def test_build_position_map_deleted_file() -> None:
    """Deleted file: no lines are mappable (all removed)."""
    pmap = build_position_map(DELETED_FILE_DIFF)
    assert pmap["src/old.py"] == {}


def test_build_position_map_empty_diff() -> None:
    """Empty diff: returns empty dict."""
    assert build_position_map("") == {}


def test_removed_lines_not_in_map() -> None:
    """Removed lines ('-') must not appear in the position map."""
    pmap = build_position_map(REMOVED_LINES_DIFF)
    file_map = pmap["src/app.py"]
    # Head side after applying diff:
    # line 1 = "import os" (context), line 2 = "import pathlib" (added),
    # line 3 = "" (context), line 4 = "def main():" (context)
    assert 1 in file_map
    assert 2 in file_map
    assert 3 in file_map
    # 4 head-side lines mapped (1,2,3,4): context+added only
    assert len(file_map) == 4


def test_context_lines_correctly_mapped() -> None:
    """Context lines (starting with ' ') are in the position map."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    file_map = pmap["src/app.py"]
    # "import os" is a context line at head line 1
    assert 1 in file_map


# ---------------------------------------------------------------------------
# Unit tests — map_finding_to_position
# ---------------------------------------------------------------------------


def test_map_finding_hit() -> None:
    """Finding on a mapped line returns a DiffPosition."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    finding = _make_finding(file="src/app.py", line=2)
    result = map_finding_to_position(finding, pmap)
    assert result is not None
    assert result.path == "src/app.py"
    assert result.line == 2
    assert result.position == 3


def test_map_finding_miss() -> None:
    """Finding on a non-mapped line returns None."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    finding = _make_finding(file="src/app.py", line=999)
    assert map_finding_to_position(finding, pmap) is None


def test_map_finding_none_line() -> None:
    """Finding with line=None returns None (file-level finding)."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    finding = _make_finding(file="src/app.py", line=None)
    assert map_finding_to_position(finding, pmap) is None


def test_map_finding_file_not_in_diff() -> None:
    """Finding for a file not in the diff returns None."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    finding = _make_finding(file="src/other.py", line=1)
    assert map_finding_to_position(finding, pmap) is None


# ---------------------------------------------------------------------------
# Unit tests — parse_diff_files
# ---------------------------------------------------------------------------


def test_parse_diff_files_empty() -> None:
    """Empty diff returns empty list."""
    assert parse_diff_files("") == []


def test_parse_diff_files_simple() -> None:
    """Single-file diff returns the file path."""
    files = parse_diff_files(SINGLE_HUNK_DIFF)
    assert files == ["src/app.py"]


def test_parse_diff_files_multi_file() -> None:
    """Multi-file diff returns all file paths in order."""
    multi_diff = SINGLE_HUNK_DIFF + "\n" + NEW_FILE_DIFF
    files = parse_diff_files(multi_diff)
    assert files == ["src/app.py", "src/new.py"]


# ---------------------------------------------------------------------------
# Integration tests — with fixtures
# ---------------------------------------------------------------------------


def test_round_trip_diff_simple(diff_simple: str) -> None:
    """diff_simple fixture: build + map round-trips for known lines."""
    pmap = build_position_map(diff_simple)
    # src/utils.py is a new file — line 1 should be mappable
    finding = _make_finding(file="src/utils.py", line=1)
    result = map_finding_to_position(finding, pmap)
    assert result is not None
    assert result.path == "src/utils.py"
    assert result.line == 1


def test_round_trip_diff_large(diff_large: str) -> None:
    """diff_large fixture: files are extracted and positions built without error."""
    files = parse_diff_files(diff_large)
    assert len(files) > 0
    pmap = build_position_map(diff_large)
    assert len(pmap) > 0


def test_parse_diff_files_large(diff_large: str) -> None:
    """diff_large fixture: parse_diff_files returns multiple files."""
    files = parse_diff_files(diff_large)
    assert len(files) >= 3


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_new_file_all_lines_mappable() -> None:
    """All added lines in a new-file diff are mappable."""
    pmap = build_position_map(NEW_FILE_DIFF)
    file_map = pmap["src/new.py"]
    for line_num in range(1, 4):
        assert line_num in file_map, f"Line {line_num} should be mappable"


def test_accept_multi_hunk_positions_correct() -> None:
    """Multi-hunk positions increment correctly through hunk boundaries."""
    pmap = build_position_map(MULTI_HUNK_DIFF)
    file_map = pmap["src/app.py"]
    # Verify positions are strictly increasing
    positions = sorted(file_map.values())
    for i in range(len(positions) - 1):
        assert positions[i] < positions[i + 1]


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def test_diff_position_is_frozen() -> None:
    """DiffPosition is a frozen dataclass — attribute assignment raises."""
    pos = DiffPosition(path="f.py", position=1, line=1)
    with pytest.raises(AttributeError):
        pos.path = "other.py"  # type: ignore[misc]
