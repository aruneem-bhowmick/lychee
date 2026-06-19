"""Regression tests verifying that the review engine has not been modified.

The review engine (src/lychee/review.py) must remain unchanged during
inline commenting work.  This module provides both hash-based and
diff-based verification to catch accidental modifications.

Framework: pytest.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

REVIEW_MODULE_PATH: Path = Path(__file__).parent.parent / "src" / "lychee" / "review.py"

# SHA-256 hash of review.py captured before inline commenting work began.
# Computed from LF-normalized content so the check is consistent across
# platforms (Windows CRLF vs Linux LF).  Update this value only when
# review.py is intentionally modified outside the inline commenting scope.
_EXPECTED_SHA256 = "00a845e881314f70389067fa922008f59140073f2dc5bb2387a3ab5cfb7bf20c"


def test_engine_review_py_unchanged() -> None:
    """Verify review.py has not been modified by computing its SHA-256 hash.

    Fails if the file content differs from the known-good hash captured
    before inline commenting development.  If review.py is intentionally
    updated for unrelated reasons, regenerate the hash and update
    ``_EXPECTED_SHA256``.
    """
    content = REVIEW_MODULE_PATH.read_bytes().replace(b"\r\n", b"\n")
    actual_hash = hashlib.sha256(content).hexdigest()
    assert actual_hash == _EXPECTED_SHA256, (
        f"review.py has been modified.\n"
        f"Expected SHA-256: {_EXPECTED_SHA256}\n"
        f"Actual SHA-256:   {actual_hash}\n"
        f"If this change is intentional, update _EXPECTED_SHA256 in "
        f"{__file__}."
    )


def test_engine_review_py_no_git_diff() -> None:
    """Verify review.py has no uncommitted or staged changes via git diff.

    Runs ``git diff HEAD -- src/lychee/review.py`` and asserts the output
    is empty, confirming no pending modifications exist.  This
    complements the hash check by catching work-in-progress edits.
    """
    result = subprocess.run(
        ["git", "diff", "HEAD", "--", str(REVIEW_MODULE_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout == "", f"review.py has uncommitted changes:\n{result.stdout}"


def test_accept_engine_code_untouched() -> None:
    """Acceptance test: review.py has zero modifications (diff-verified).

    Combines both file-existence and hash verification to confirm the
    engine module is untouched.
    """
    assert REVIEW_MODULE_PATH.exists(), f"review.py not found at {REVIEW_MODULE_PATH}"

    content = REVIEW_MODULE_PATH.read_bytes().replace(b"\r\n", b"\n")
    actual_hash = hashlib.sha256(content).hexdigest()
    assert actual_hash == _EXPECTED_SHA256, "review.py has been modified (acceptance check failed)."
