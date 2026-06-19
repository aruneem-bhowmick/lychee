"""Exhaustive tests for lychee.diff_mapping.

Covers build_position_map(), map_finding_to_position(), parse_diff_files(),
and the DiffPosition dataclass.  Tests use inline diff strings and the
shared diff fixture files from tests/fixtures/.

Framework: pytest.  Coverage target: >= 90% on src/lychee/diff_mapping.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lychee.diff_mapping import (
    DiffPosition,
    build_position_map,
    map_finding_to_position,
    parse_diff_files,
)

FIXTURES_DIR: Path = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Inline diff constants
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

MULTI_FILE_DIFF = """\
diff --git a/src/app.py b/src/app.py
index aaa..bbb 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
 import os
+import sys

 def main():
diff --git a/src/utils.py b/src/utils.py
index ccc..ddd 100644
--- a/src/utils.py
+++ b/src/utils.py
@@ -5,3 +5,4 @@

 def helper():
+    # added line
     pass
"""

ADDED_FILE_DIFF = """\
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

BINARY_FILE_DIFF = """\
diff --git a/assets/logo.png b/assets/logo.png
new file mode 100644
index 0000000..abcdef1
Binary files /dev/null and b/assets/logo.png differ
"""

NO_NEWLINE_DIFF = """\
diff --git a/src/app.py b/src/app.py
index aaa..bbb 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,3 @@
 import os

-def main(): pass
+def main(): return 0
\\ No newline at end of file
"""

RENAMED_FILE_DIFF = """\
diff --git a/src/old_name.py b/src/new_name.py
similarity index 90%
rename from src/old_name.py
rename to src/new_name.py
index aaa..bbb 100644
--- a/src/old_name.py
+++ b/src/new_name.py
@@ -1,3 +1,4 @@
 import os
+import sys

 def main():
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

MIXED_LINES_DIFF = """\
diff --git a/src/app.py b/src/app.py
index aaa..bbb 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,7 +1,7 @@
 line_one
-removed_a
+added_a
 line_three
-removed_b
-removed_c
+added_b
+added_c
 line_six
"""


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _load_fixture(name: str) -> str:
    """Load a diff fixture file from the fixtures directory."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_diff_mapping_importable() -> None:
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
# Sanity tests
# ---------------------------------------------------------------------------


def test_position_always_positive() -> None:
    """Every DiffPosition.position in a non-empty map is >= 1."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    for file_map in pmap.values():
        for dp in file_map.values():
            assert dp.position >= 1


def test_head_line_always_positive() -> None:
    """Every DiffPosition.head_line in a non-empty map is >= 1."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    for file_map in pmap.values():
        for dp in file_map.values():
            assert dp.head_line >= 1


# ---------------------------------------------------------------------------
# Unit tests — build_position_map
# ---------------------------------------------------------------------------


def test_build_position_map_single_hunk() -> None:
    """Single hunk: added and context lines are mapped with correct positions."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    assert "src/app.py" in pmap
    file_map = pmap["src/app.py"]
    # Position 1 = " import os" (context, head line 1)
    assert file_map[1].position == 1
    assert file_map[1].head_line == 1
    # Position 2 = "+import sys" (added, head line 2)
    assert file_map[2].position == 2
    assert file_map[2].head_line == 2
    # Position 3 = " " (context, head line 3)
    assert file_map[3].position == 3
    # Position 4 = " def main():" (context, head line 4)
    assert file_map[4].position == 4


def test_build_position_map_multi_hunk() -> None:
    """Multi-hunk: position counter continues across hunk boundaries.

    Subsequent @@ headers increment the position, so the first line after
    the second hunk header has a position that accounts for all prior lines
    plus the second hunk header itself.
    """
    pmap = build_position_map(MULTI_HUNK_DIFF)
    file_map = pmap["src/app.py"]

    # First hunk (@@ -1,3 +1,4 @@): position starts at 1
    # " import os" → pos 1, head 1
    assert file_map[1].position == 1
    # "+import sys" → pos 2, head 2
    assert file_map[2].position == 2
    # " " → pos 3, head 3
    assert file_map[3].position == 3
    # " def main():" → pos 4, head 4
    assert file_map[4].position == 4

    # Second hunk header (@@ -10,3 +11,4 @@) → pos 5
    # "     pass" → pos 6, head 11
    assert file_map[11].position == 6
    # " " → pos 7, head 12
    assert file_map[12].position == 7
    # "+# new comment" → pos 8, head 13
    assert file_map[13].position == 8
    # " x = 1" → pos 9, head 14
    assert file_map[14].position == 9


def test_build_position_map_multi_file() -> None:
    """Multi-file diff: each file has its own position map."""
    pmap = build_position_map(MULTI_FILE_DIFF)
    assert "src/app.py" in pmap
    assert "src/utils.py" in pmap
    # Each file's positions start from 1 independently
    assert pmap["src/app.py"][1].position == 1
    assert pmap["src/utils.py"][5].position == 1


def test_build_position_map_added_file() -> None:
    """Added file (--- /dev/null): all lines are + lines and mappable."""
    pmap = build_position_map(ADDED_FILE_DIFF)
    assert "src/new.py" in pmap
    file_map = pmap["src/new.py"]
    assert file_map[1].position == 1
    assert file_map[2].position == 2
    assert file_map[3].position == 3
    assert len(file_map) == 3


def test_build_position_map_deleted_file() -> None:
    """Deleted file (+++ /dev/null): no mappable positions."""
    pmap = build_position_map(DELETED_FILE_DIFF)
    # Deleted files should not appear in the map since +++ is /dev/null
    assert "src/old.py" not in pmap


def test_build_position_map_binary_file() -> None:
    """Binary file marker: no positions for that file."""
    pmap = build_position_map(BINARY_FILE_DIFF)
    # Binary files have no +++ header with a real path, so not in map
    assert len(pmap) == 0


def test_build_position_map_no_newline_marker() -> None:
    r"""'\ No newline at end of file' does not increment position."""
    pmap = build_position_map(NO_NEWLINE_DIFF)
    file_map = pmap["src/app.py"]
    # " import os" → pos 1, head 1
    assert file_map[1].position == 1
    # " " → pos 2, head 2
    assert file_map[2].position == 2
    # "-def main(): pass" → pos 3 (removed, not in map)
    # "+def main(): return 0" → pos 4, head 3
    assert file_map[3].position == 4
    # "\ No newline..." should NOT increment position
    assert len(file_map) == 3  # only 3 head-side lines mapped


def test_build_position_map_renamed_file() -> None:
    """Renamed file: uses the new-side path from +++ header."""
    pmap = build_position_map(RENAMED_FILE_DIFF)
    # Old name should not be in the map
    assert "src/old_name.py" not in pmap
    # New name should be in the map
    assert "src/new_name.py" in pmap
    file_map = pmap["src/new_name.py"]
    assert file_map[1].path == "src/new_name.py"


def test_build_position_map_empty_diff() -> None:
    """Empty diff string returns empty dict."""
    assert build_position_map("") == {}


def test_build_position_map_context_lines_map_to_head() -> None:
    """Context lines (starting with ' ') produce correct head line numbers."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    file_map = pmap["src/app.py"]
    # " import os" is a context line at head line 1
    dp = file_map[1]
    assert dp.head_line == 1
    assert dp.path == "src/app.py"


def test_build_position_map_removed_lines_not_mapped() -> None:
    """Removed lines ('-') must not appear in the position map."""
    pmap = build_position_map(REMOVED_LINES_DIFF)
    file_map = pmap["src/app.py"]
    # Head side after applying diff:
    # line 1 = "import os" (context), line 2 = "import pathlib" (added),
    # line 3 = "" (context)
    assert 1 in file_map  # context "import os"
    assert 2 in file_map  # added "import pathlib"
    assert 3 in file_map  # context ""
    # Removed lines are not on the head side, so no extra mappings
    # "import sys" and "import re" were removed — not mappable
    # But "def main():" at head line 4 is still a context line if in the hunk
    # In this diff, @@ -1,5 +1,3 @@ means 3 head lines starting at 1

    # Verify removed lines didn't produce any entries with wrong head lines
    head_lines = sorted(file_map.keys())
    for hl in head_lines:
        assert file_map[hl].head_line == hl


def test_head_line_tracking_across_mixed_lines() -> None:
    """Interleaved added/removed/context lines: head line numbers are correct."""
    pmap = build_position_map(MIXED_LINES_DIFF)
    file_map = pmap["src/app.py"]

    # @@ -1,7 +1,7 @@ → head starts at 1
    # " line_one"      → pos 1, head 1 (context)
    assert file_map[1].head_line == 1
    assert file_map[1].position == 1

    # "-removed_a"     → pos 2 (removed, not mapped, head stays 2)
    # "+added_a"       → pos 3, head 2 (added)
    assert file_map[2].head_line == 2
    assert file_map[2].position == 3

    # " line_three"    → pos 4, head 3 (context)
    assert file_map[3].head_line == 3
    assert file_map[3].position == 4

    # "-removed_b"     → pos 5 (removed)
    # "-removed_c"     → pos 6 (removed)
    # "+added_b"       → pos 7, head 4
    assert file_map[4].head_line == 4
    assert file_map[4].position == 7

    # "+added_c"       → pos 8, head 5
    assert file_map[5].head_line == 5
    assert file_map[5].position == 8

    # " line_six"      → pos 9, head 6
    assert file_map[6].head_line == 6
    assert file_map[6].position == 9


# ---------------------------------------------------------------------------
# Unit tests — map_finding_to_position
# ---------------------------------------------------------------------------


def test_map_finding_to_position_happy_path() -> None:
    """File + line that exists in the map returns the correct DiffPosition."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    result = map_finding_to_position("src/app.py", 2, pmap)
    assert result is not None
    assert result.path == "src/app.py"
    assert result.head_line == 2
    assert result.position == 2


def test_map_finding_to_position_line_none() -> None:
    """line=None returns None."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    assert map_finding_to_position("src/app.py", None, pmap) is None


def test_map_finding_to_position_file_not_in_diff() -> None:
    """File not in the diff map returns None."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    assert map_finding_to_position("src/other.py", 1, pmap) is None


def test_map_finding_to_position_line_not_in_hunk() -> None:
    """Line exists in the file but is not in any hunk; returns None."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    # Line 999 is far beyond the hunk range
    assert map_finding_to_position("src/app.py", 999, pmap) is None


# ---------------------------------------------------------------------------
# Unit tests — parse_diff_files
# ---------------------------------------------------------------------------


def test_parse_diff_files_returns_new_side_paths() -> None:
    """Verify file path extraction returns new-side paths."""
    files = parse_diff_files(SINGLE_HUNK_DIFF)
    assert files == ["src/app.py"]


def test_parse_diff_files_empty_diff() -> None:
    """Empty diff string returns empty list."""
    assert parse_diff_files("") == []


def test_parse_diff_files_multi_file() -> None:
    """Multi-file diff returns all file paths in order."""
    files = parse_diff_files(MULTI_FILE_DIFF)
    assert files == ["src/app.py", "src/utils.py"]


def test_parse_diff_files_excludes_deleted() -> None:
    """Deleted file (+++ /dev/null) is not included in the file list."""
    files = parse_diff_files(DELETED_FILE_DIFF)
    assert files == []


def test_parse_diff_files_added_file() -> None:
    """Added file (--- /dev/null) is included with the new-side path."""
    files = parse_diff_files(ADDED_FILE_DIFF)
    assert files == ["src/new.py"]


def test_parse_diff_files_renamed() -> None:
    """Renamed file returns the new-side path only."""
    files = parse_diff_files(RENAMED_FILE_DIFF)
    assert files == ["src/new_name.py"]


# ---------------------------------------------------------------------------
# Integration tests — with fixture files
# ---------------------------------------------------------------------------


def test_fixture_simple_patch() -> None:
    """diff_simple.patch: build + map round-trips for known lines."""
    diff = _load_fixture("diff_simple.patch")
    pmap = build_position_map(diff)
    assert "src/app.py" in pmap

    # "+import sys" is head line 4 in the fixture
    result = map_finding_to_position("src/app.py", 4, pmap)
    assert result is not None
    assert result.position == 4


def test_fixture_multi_hunk_patch() -> None:
    """diff_multi_hunk.patch: positions span across three hunks correctly."""
    diff = _load_fixture("diff_multi_hunk.patch")
    pmap = build_position_map(diff)
    assert "src/server.py" in pmap
    file_map = pmap["src/server.py"]

    # Verify entries exist across all three hunks
    # First hunk starts at head line 1
    assert 1 in file_map
    # Second hunk starts at head line 21
    assert 21 in file_map or 22 in file_map or 23 in file_map
    # Third hunk starts at head line 37
    assert 37 in file_map or 38 in file_map or 39 in file_map or 40 in file_map


def test_fixture_multi_file_patch() -> None:
    """diff_multi_file.patch: files extracted correctly."""
    diff = _load_fixture("diff_multi_file.patch")
    files = parse_diff_files(diff)
    # Should include config, newmodule, test_config but NOT legacy (deleted)
    assert "src/config.py" in files
    assert "src/newmodule.py" in files
    assert "tests/test_config.py" in files
    assert "src/legacy.py" not in files


def test_fixture_multi_file_position_maps() -> None:
    """diff_multi_file.patch: each file has independent position maps."""
    diff = _load_fixture("diff_multi_file.patch")
    pmap = build_position_map(diff)
    assert "src/config.py" in pmap
    assert "src/newmodule.py" in pmap
    assert "tests/test_config.py" in pmap
    # Deleted file should not be in the position map
    assert "src/legacy.py" not in pmap

    # Each file starts positions from 1
    for file_map in pmap.values():
        positions = [dp.position for dp in file_map.values()]
        if positions:
            assert min(positions) == 1


# ---------------------------------------------------------------------------
# Integration tests — with conftest fixtures
# ---------------------------------------------------------------------------


def test_round_trip_diff_simple(diff_simple: str) -> None:
    """diff_simple conftest fixture: build + map round-trips for known lines."""
    pmap = build_position_map(diff_simple)
    # src/utils.py is a new file — line 1 should be mappable
    result = map_finding_to_position("src/utils.py", 1, pmap)
    assert result is not None
    assert result.path == "src/utils.py"
    assert result.head_line == 1


def test_round_trip_diff_large(diff_large: str) -> None:
    """diff_large fixture: files are extracted and positions built without error."""
    files = parse_diff_files(diff_large)
    assert len(files) > 0
    pmap = build_position_map(diff_large)
    assert len(pmap) > 0


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_changed_line_findings_map_correctly() -> None:
    """Construct a realistic diff and findings; all map to correct positions."""
    diff = _load_fixture("diff_multi_hunk.patch")
    pmap = build_position_map(diff)
    file_map = pmap["src/server.py"]

    # Check that several known head lines are mappable
    for head_line, dp in file_map.items():
        result = map_finding_to_position("src/server.py", head_line, pmap)
        assert result is not None
        assert result.head_line == head_line
        assert result.position == dp.position


def test_accept_mapping_covers_added_and_context() -> None:
    """Both added (+) and context ( ) lines are in the map."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    file_map = pmap["src/app.py"]

    # Line 1 "import os" is context
    assert 1 in file_map
    # Line 2 "import sys" is added
    assert 2 in file_map


def test_accept_multi_hunk_positions_correct() -> None:
    """Multi-hunk file maps all lines correctly, including the gap between hunks."""
    pmap = build_position_map(MULTI_HUNK_DIFF)
    file_map = pmap["src/app.py"]

    # Verify positions are strictly increasing across all mapped lines
    entries = sorted(file_map.items(), key=lambda kv: kv[1].position)
    for i in range(len(entries) - 1):
        assert entries[i][1].position < entries[i + 1][1].position

    # Verify the gap: lines 5-10 (between hunks) are not mapped
    for gap_line in range(5, 11):
        assert gap_line not in file_map


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def test_position_map_snapshot_simple_diff() -> None:
    """Golden snapshot of the position map for the single-hunk inline diff."""
    pmap = build_position_map(SINGLE_HUNK_DIFF)
    expected = {
        "src/app.py": {
            1: DiffPosition(path="src/app.py", position=1, head_line=1),
            2: DiffPosition(path="src/app.py", position=2, head_line=2),
            3: DiffPosition(path="src/app.py", position=3, head_line=3),
            4: DiffPosition(path="src/app.py", position=4, head_line=4),
        }
    }
    assert pmap == expected


def test_position_map_snapshot_multi_hunk() -> None:
    """Golden snapshot for the multi-hunk inline diff."""
    pmap = build_position_map(MULTI_HUNK_DIFF)
    expected = {
        "src/app.py": {
            1: DiffPosition(path="src/app.py", position=1, head_line=1),
            2: DiffPosition(path="src/app.py", position=2, head_line=2),
            3: DiffPosition(path="src/app.py", position=3, head_line=3),
            4: DiffPosition(path="src/app.py", position=4, head_line=4),
            11: DiffPosition(path="src/app.py", position=6, head_line=11),
            12: DiffPosition(path="src/app.py", position=7, head_line=12),
            13: DiffPosition(path="src/app.py", position=8, head_line=13),
            14: DiffPosition(path="src/app.py", position=9, head_line=14),
        }
    }
    assert pmap == expected


def test_diff_position_is_frozen() -> None:
    """DiffPosition is a frozen dataclass — attribute assignment raises."""
    pos = DiffPosition(path="f.py", position=1, head_line=1)
    with pytest.raises(AttributeError):
        pos.path = "other.py"  # type: ignore[misc]


def test_diff_position_fields() -> None:
    """DiffPosition has path, position, and head_line fields."""
    pos = DiffPosition(path="f.py", position=3, head_line=10)
    assert pos.path == "f.py"
    assert pos.position == 3
    assert pos.head_line == 10
