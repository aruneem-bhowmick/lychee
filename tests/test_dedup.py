"""Unit, integration, system, acceptance, regression, smoke, and e2e tests for lychee.dedup.

Covers cross-push deduplication logic: fingerprint computation, finding
identity comparison, state serialisation, and the full dedup pipeline.
All tests are deterministic with no I/O or network dependencies.

Framework: pytest.  Coverage target: >= 90% on src/lychee/dedup.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from lychee.dedup import (
    FindingFingerprint,
    build_inline_state,
    compute_message_hash,
    deduplicate_findings,
    extract_previous_fingerprints,
)
from lychee.models import Category, Finding, ReviewResult, Ripeness, Severity
from lychee.poster import InlineReviewPoster

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    file: str = "src/app.py",
    line: int | None = 2,
    severity: Severity = Severity.minor,
    category: Category = Category.style,
    message: str = "Test finding.",
    suggestion: str | None = None,
) -> Finding:
    """Create a Finding for dedup tests."""
    return Finding(
        file=file,
        line=line,
        severity=severity,
        category=category,
        message=message,
        suggestion=suggestion,
    )


def _make_review_result(findings: list[Finding] | None = None) -> ReviewResult:
    """Create a ReviewResult with optional findings."""
    return ReviewResult(
        ripeness=Ripeness.ripe,
        summary="Test summary.",
        walkthrough="Test walkthrough.",
        findings=findings or [],
        model="test-model",
        usage={"input_tokens": 100, "output_tokens": 50},
    )


# Minimal diff where src/app.py lines 1 and 2 are in the diff.
_INLINE_DIFF = """\
diff --git a/src/app.py b/src/app.py
index aaa..bbb 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
 import os
+import sys

 def main():
"""


def _make_mock_pr(review_id: int = 200) -> MagicMock:
    """Create a mock PullRequest with create_review support."""
    pr = MagicMock()
    pr.get_issue_comments.return_value = []
    mock_review = MagicMock()
    mock_review.id = review_id
    pr.create_review.return_value = mock_review
    return pr


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_dedup_module_importable() -> None:
    """Core dedup symbols import cleanly from lychee.dedup."""  # P3-R3
    from lychee.dedup import (
        FindingFingerprint,
        build_inline_state,
        deduplicate_findings,
    )

    assert callable(deduplicate_findings)
    assert callable(build_inline_state)
    assert callable(FindingFingerprint)


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_fingerprint_constructs() -> None:
    """FindingFingerprint constructs without error."""  # P3-R3
    fp = FindingFingerprint(
        file="src/app.py", line=10, severity="minor", message_hash="abcdef123456"
    )
    assert fp.file == "src/app.py"
    assert fp.line == 10


# ---------------------------------------------------------------------------
# Unit tests — compute_message_hash
# ---------------------------------------------------------------------------


def test_compute_message_hash_deterministic() -> None:
    """Same message produces the same hash across calls."""  # P3-R3
    msg = "Unused import detected."
    assert compute_message_hash(msg) == compute_message_hash(msg)


def test_compute_message_hash_different_messages() -> None:
    """Different messages produce different hashes."""  # P3-R3
    h1 = compute_message_hash("First message.")
    h2 = compute_message_hash("Second message.")
    assert h1 != h2


def test_compute_message_hash_strips_whitespace() -> None:
    """Leading and trailing whitespace is ignored."""  # P3-R3
    base = "  Trailing space check.  "
    assert compute_message_hash(base) == compute_message_hash(base.strip())


def test_compute_message_hash_length() -> None:
    """Hash is exactly 12 hex characters."""  # P3-R3
    h = compute_message_hash("Any message.")
    assert len(h) == 12
    assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# Unit tests — FindingFingerprint
# ---------------------------------------------------------------------------


def test_fingerprint_from_finding() -> None:
    """from_finding constructs a fingerprint from a Finding."""  # P3-R3
    finding = _make_finding(
        file="src/main.py", line=5, severity=Severity.major, message="Bug here."
    )
    fp = FindingFingerprint.from_finding(finding)
    assert fp.file == "src/main.py"
    assert fp.line == 5
    assert fp.severity == "major"
    assert fp.message_hash == compute_message_hash("Bug here.")


def test_fingerprint_equality() -> None:
    """Same fields = equal; different fields = not equal."""  # P3-R3
    fp1 = FindingFingerprint(file="a.py", line=1, severity="minor", message_hash="aaa111bbb222")
    fp2 = FindingFingerprint(file="a.py", line=1, severity="minor", message_hash="aaa111bbb222")
    fp3 = FindingFingerprint(file="b.py", line=1, severity="minor", message_hash="aaa111bbb222")
    assert fp1 == fp2
    assert fp1 != fp3


def test_fingerprint_hashable() -> None:
    """FindingFingerprint can be added to a set."""  # P3-R3
    fp = FindingFingerprint(file="a.py", line=1, severity="minor", message_hash="aaa111bbb222")
    s = {fp}
    assert fp in s
    assert len(s) == 1


def test_fingerprint_round_trip() -> None:
    """from_dict(to_dict(fp)) is lossless."""  # P3-R3
    fp = FindingFingerprint(
        file="src/app.py", line=42, severity="critical", message_hash="deadbeef0123"
    )
    assert FindingFingerprint.from_dict(fp.to_dict()) == fp


def test_fingerprint_round_trip_none_line() -> None:
    """from_dict(to_dict(fp)) preserves None line."""  # P3-R3
    fp = FindingFingerprint(
        file="src/app.py", line=None, severity="info", message_hash="123456789abc"
    )
    assert FindingFingerprint.from_dict(fp.to_dict()) == fp


# ---------------------------------------------------------------------------
# Unit tests — deduplicate_findings
# ---------------------------------------------------------------------------


def test_deduplicate_findings_no_previous() -> None:
    """Empty previous list; all findings are to_post."""  # P3-R3
    findings = [_make_finding(message="A"), _make_finding(message="B")]
    to_post, already = deduplicate_findings(findings, [])
    assert len(to_post) == 2
    assert len(already) == 0


def test_deduplicate_findings_all_duplicates() -> None:
    """All new findings match previous; to_post is empty."""  # P3-R3
    finding = _make_finding(file="src/app.py", line=2, severity=Severity.minor, message="Dup msg.")
    fp = FindingFingerprint.from_finding(finding)
    to_post, already = deduplicate_findings([finding], [fp])
    assert len(to_post) == 0
    assert len(already) == 1


def test_deduplicate_findings_mixed() -> None:
    """Some match, some don't; correctly partitioned."""  # P3-R3
    f_dup = _make_finding(file="src/app.py", line=2, severity=Severity.minor, message="Existing.")
    f_new = _make_finding(file="src/app.py", line=2, severity=Severity.minor, message="Brand new.")
    fp_dup = FindingFingerprint.from_finding(f_dup)
    to_post, already = deduplicate_findings([f_dup, f_new], [fp_dup])
    assert len(to_post) == 1
    assert to_post[0].message == "Brand new."
    assert len(already) == 1
    assert already[0].message == "Existing."


def test_deduplicate_findings_different_line_same_message() -> None:
    """Different line = not a duplicate."""  # P3-R3
    f_old = _make_finding(line=5, message="Same msg.")
    f_new = _make_finding(line=10, message="Same msg.")
    fp_old = FindingFingerprint.from_finding(f_old)
    to_post, already = deduplicate_findings([f_new], [fp_old])
    assert len(to_post) == 1
    assert len(already) == 0


def test_deduplicate_findings_same_line_different_message() -> None:
    """Different message = not a duplicate."""  # P3-R3
    f_old = _make_finding(line=5, message="Old message.")
    f_new = _make_finding(line=5, message="New message.")
    fp_old = FindingFingerprint.from_finding(f_old)
    to_post, already = deduplicate_findings([f_new], [fp_old])
    assert len(to_post) == 1
    assert len(already) == 0


def test_deduplicate_findings_same_line_different_severity() -> None:
    """Different severity = not a duplicate."""  # P3-R3
    f_old = _make_finding(line=5, severity=Severity.minor, message="Check.")
    f_new = _make_finding(line=5, severity=Severity.major, message="Check.")
    fp_old = FindingFingerprint.from_finding(f_old)
    to_post, already = deduplicate_findings([f_new], [fp_old])
    assert len(to_post) == 1
    assert len(already) == 0


# ---------------------------------------------------------------------------
# Unit tests — build_inline_state
# ---------------------------------------------------------------------------


def test_build_inline_state() -> None:
    """Returns dict with last_reviewed_sha and inline_findings list."""  # P3-R3
    findings = [_make_finding(message="A"), _make_finding(message="B")]
    state = build_inline_state(findings, "sha123")
    assert state["last_reviewed_sha"] == "sha123"
    assert isinstance(state["inline_findings"], list)
    assert len(state["inline_findings"]) == 2
    for entry in state["inline_findings"]:
        assert "file" in entry
        assert "line" in entry
        assert "severity" in entry
        assert "message_hash" in entry


# ---------------------------------------------------------------------------
# Unit tests — extract_previous_fingerprints
# ---------------------------------------------------------------------------


def test_extract_previous_fingerprints_valid_state() -> None:
    """Extracts fingerprints correctly from a well-formed state dict."""  # P3-R3
    fp = FindingFingerprint(file="a.py", line=1, severity="minor", message_hash="aaa111bbb222")
    state = {"inline_findings": [fp.to_dict()]}
    result = extract_previous_fingerprints(state)
    assert len(result) == 1
    assert result[0] == fp


def test_extract_previous_fingerprints_none_state() -> None:
    """Returns empty list when state is None."""  # P3-R3
    assert extract_previous_fingerprints(None) == []


def test_extract_previous_fingerprints_missing_key() -> None:
    """State without inline_findings returns empty list."""  # P3-R3
    assert extract_previous_fingerprints({"last_reviewed_sha": "abc"}) == []


def test_extract_previous_fingerprints_malformed() -> None:
    """Corrupted inline_findings returns empty list (no crash)."""  # P3-R3
    # Non-list value
    assert extract_previous_fingerprints({"inline_findings": "not a list"}) == []
    # List with malformed entries (missing keys)
    assert extract_previous_fingerprints({"inline_findings": [{"bad": "data"}]}) == []
    # List with non-dict entries
    assert extract_previous_fingerprints({"inline_findings": [42, None]}) == []


def test_extract_previous_fingerprints_partial_malformed() -> None:
    """Mix of valid and invalid entries: valid ones extracted, invalid skipped."""  # P3-R3
    valid = {
        "file": "a.py",
        "line": 1,
        "severity": "minor",
        "message_hash": "aaa111bbb222",
    }
    invalid = {"bad": "data"}
    result = extract_previous_fingerprints({"inline_findings": [valid, invalid]})
    assert len(result) == 1
    assert result[0].file == "a.py"


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_inline_poster_dedup_skips_duplicates() -> None:
    """Post with previous state skips duplicate findings."""  # P3-R3
    pr = _make_mock_pr()
    # Finding on line 2 (mappable in _INLINE_DIFF)
    finding = _make_finding(file="src/app.py", line=2, message="Already posted.")
    result = _make_review_result([finding])
    poster = InlineReviewPoster(MagicMock())

    # Build previous state containing this exact finding's fingerprint
    previous_state = build_inline_state([finding], "old_sha")

    post_result = poster.post(pr, result, _INLINE_DIFF, previous_state=previous_state)

    # Should skip the duplicate — no review created
    assert post_result.review_id is None
    assert post_result.inline_count == 0
    pr.create_review.assert_not_called()


def test_inline_poster_dedup_no_previous_state() -> None:
    """Post with previous_state=None posts all mappable findings."""  # P3-R3
    pr = _make_mock_pr()
    finding = _make_finding(file="src/app.py", line=2, message="New finding.")
    result = _make_review_result([finding])
    poster = InlineReviewPoster(MagicMock())

    post_result = poster.post(pr, result, _INLINE_DIFF, previous_state=None)

    assert post_result.review_id == 200
    assert post_result.inline_count == 1
    pr.create_review.assert_called_once()


def test_inline_poster_dedup_all_duplicates_no_review() -> None:
    """When all findings are duplicates, create_review is not called."""  # P3-R3
    pr = _make_mock_pr()
    f1 = _make_finding(file="src/app.py", line=2, message="Dup 1.")
    f2 = _make_finding(file="src/app.py", line=1, message="Dup 2.")
    result = _make_review_result([f1, f2])
    poster = InlineReviewPoster(MagicMock())

    previous_state = build_inline_state([f1, f2], "old_sha")
    post_result = poster.post(pr, result, _INLINE_DIFF, previous_state=previous_state)

    assert post_result.review_id is None
    assert post_result.inline_count == 0
    pr.create_review.assert_not_called()


def test_inline_poster_dedup_posts_only_new() -> None:
    """With mixed findings, only new ones are posted."""  # P3-R3
    pr = _make_mock_pr()
    f_old = _make_finding(file="src/app.py", line=2, message="Old finding.")
    f_new = _make_finding(file="src/app.py", line=2, message="New finding.")
    result = _make_review_result([f_old, f_new])
    poster = InlineReviewPoster(MagicMock())

    previous_state = build_inline_state([f_old], "old_sha")
    post_result = poster.post(pr, result, _INLINE_DIFF, previous_state=previous_state)

    assert post_result.inline_count == 1
    assert post_result.posted_findings[0].message == "New finding."
    pr.create_review.assert_called_once()
    # Verify only one comment was submitted
    comments = pr.create_review.call_args.kwargs["comments"]
    assert len(comments) == 1


# ---------------------------------------------------------------------------
# System tests
# ---------------------------------------------------------------------------


def test_system_dedup_across_two_reviews() -> None:
    """Simulate two sequential reviews: second posts only new findings."""  # P3-R3
    # First review: post all findings
    f1 = _make_finding(file="src/app.py", line=2, message="Style issue.")
    f2 = _make_finding(file="src/app.py", line=1, message="Naming issue.")

    result1 = _make_review_result([f1, f2])
    pr1 = _make_mock_pr()
    poster = InlineReviewPoster(MagicMock())

    post1 = poster.post(pr1, result1, _INLINE_DIFF)
    assert post1.inline_count == 2

    # Build state from first review
    state = build_inline_state(post1.posted_findings, "sha_v1")

    # Second review: same findings plus one new
    f3 = _make_finding(file="src/app.py", line=2, message="Performance note.")
    result2 = _make_review_result([f1, f2, f3])
    pr2 = _make_mock_pr()

    post2 = poster.post(pr2, result2, _INLINE_DIFF, previous_state=state)
    assert post2.inline_count == 1
    assert post2.posted_findings[0].message == "Performance note."


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_repush_only_new_comments() -> None:
    """Re-push posts only findings on new/changed lines."""  # P3-R3
    # First review
    f_existing = _make_finding(file="src/app.py", line=2, message="Existing issue.")
    pr = _make_mock_pr()
    poster = InlineReviewPoster(MagicMock())

    post1 = poster.post(pr, _make_review_result([f_existing]), _INLINE_DIFF)
    state = build_inline_state(post1.posted_findings, "sha_v1")

    # Re-push: same finding + new finding
    f_new = _make_finding(file="src/app.py", line=1, message="New on changed line.")
    pr2 = _make_mock_pr()
    post2 = poster.post(
        pr2,
        _make_review_result([f_existing, f_new]),
        _INLINE_DIFF,
        previous_state=state,
    )

    assert post2.inline_count == 1
    assert post2.posted_findings[0].message == "New on changed line."


def test_accept_no_repeat_comments() -> None:
    """No finding fingerprint appears in both posted and to_post."""  # P3-R3
    # First review posts some findings
    findings_v1 = [
        _make_finding(file="src/app.py", line=2, message="Issue A."),
        _make_finding(file="src/app.py", line=1, message="Issue B."),
    ]
    state = build_inline_state(findings_v1, "sha_v1")
    prev_fps = set(extract_previous_fingerprints(state))

    # Second review with overlapping findings
    findings_v2 = [
        _make_finding(file="src/app.py", line=2, message="Issue A."),
        _make_finding(file="src/app.py", line=2, message="Issue C."),
    ]
    to_post, already = deduplicate_findings(findings_v2, list(prev_fps))
    to_post_fps = {FindingFingerprint.from_finding(f) for f in to_post}

    # No overlap between posted and to_post
    assert prev_fps.isdisjoint(to_post_fps) or len(to_post_fps - prev_fps) == len(to_post_fps)
    # The duplicate was caught
    assert len(already) == 1
    assert already[0].message == "Issue A."


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def test_fingerprint_snapshot() -> None:
    """Golden snapshot of FindingFingerprint.to_dict() for a fixed Finding."""  # P3-R3
    finding = _make_finding(
        file="src/main.py",
        line=42,
        severity=Severity.major,
        category=Category.security,
        message="SQL injection risk.",
    )
    fp = FindingFingerprint.from_finding(finding)
    expected = {
        "file": "src/main.py",
        "line": 42,
        "severity": "major",
        "message_hash": compute_message_hash("SQL injection risk."),
    }
    assert fp.to_dict() == expected


def test_inline_state_snapshot() -> None:
    """Golden snapshot of build_inline_state() output for fixed inputs."""  # P3-R3
    findings = [
        _make_finding(
            file="src/app.py",
            line=10,
            severity=Severity.minor,
            message="Style issue.",
        )
    ]
    state = build_inline_state(findings, "abc123def456")
    expected = {
        "last_reviewed_sha": "abc123def456",
        "inline_findings": [
            {
                "file": "src/app.py",
                "line": 10,
                "severity": "minor",
                "message_hash": compute_message_hash("Style issue."),
            }
        ],
    }
    assert state == expected


# ---------------------------------------------------------------------------
# Sanity — existing poster tests unchanged
# ---------------------------------------------------------------------------


def test_existing_poster_tests_still_pass() -> None:
    """SummaryPoster and InlineReviewPoster import without error."""  # P3-R3
    from lychee.poster import InlinePostResult, InlineReviewPoster, SummaryPoster

    assert callable(SummaryPoster)
    assert callable(InlineReviewPoster)
    assert InlinePostResult is not None


# ---------------------------------------------------------------------------
# End-to-end test
# ---------------------------------------------------------------------------


def test_e2e_dedup_dry_run() -> None:
    """Full dedup path: build result, post, extract state, re-run, verify dedup."""  # P3-R3
    poster = InlineReviewPoster(MagicMock())

    # --- First review ---
    f1 = _make_finding(file="src/app.py", line=2, message="Lint warning A.")
    f2 = _make_finding(file="src/app.py", line=1, message="Lint warning B.")
    result_v1 = _make_review_result([f1, f2])
    pr1 = _make_mock_pr()

    post1 = poster.post(pr1, result_v1, _INLINE_DIFF)
    assert post1.inline_count == 2
    assert len(post1.posted_findings) == 2

    # Build state from first review
    state = build_inline_state(post1.posted_findings, "sha_v1")

    # Verify state round-trips through extraction
    extracted_fps = extract_previous_fingerprints(state)
    assert len(extracted_fps) == 2

    # --- Second review with overlapping findings ---
    f3 = _make_finding(file="src/app.py", line=2, message="New lint warning C.")
    result_v2 = _make_review_result([f1, f2, f3])
    pr2 = _make_mock_pr()

    post2 = poster.post(pr2, result_v2, _INLINE_DIFF, previous_state=state)
    assert post2.inline_count == 1
    assert post2.posted_findings[0].message == "New lint warning C."

    # Verify dedup correctness: no fingerprint overlap
    v1_fps = {FindingFingerprint.from_finding(f) for f in post1.posted_findings}
    v2_fps = {FindingFingerprint.from_finding(f) for f in post2.posted_findings}
    assert v1_fps.isdisjoint(v2_fps)
