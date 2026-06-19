"""Cross-push deduplication for inline review findings.

Compares new findings against previously posted findings (stored in the
state marker) to avoid re-posting duplicate inline comments on re-push.
A finding is considered a duplicate when file, line, severity, and
message hash all match a previously posted fingerprint.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from lychee.models import Finding

_logger = logging.getLogger(__name__)


def compute_message_hash(message: str) -> str:
    """Compute a short identity hash of a finding message.

    Returns the first 12 hex characters of SHA-256(message.strip().encode()).
    Deterministic and collision-resistant for practical per-PR finding counts.
    """
    return hashlib.sha256(message.strip().encode()).hexdigest()[:12]


@dataclass(frozen=True)
class FindingFingerprint:
    """Identity fingerprint for a finding, used for cross-push dedup.

    Two fingerprints match when all four fields are equal.  The frozen
    dataclass provides ``__eq__`` and ``__hash__`` for set membership.
    """

    file: str
    line: int | None
    severity: str
    message_hash: str

    @classmethod
    def from_finding(cls, finding: Finding) -> FindingFingerprint:
        """Create a fingerprint from a Finding."""
        return cls(
            file=finding.file,
            line=finding.line,
            severity=finding.severity.value,
            message_hash=compute_message_hash(finding.message),
        )

    def to_dict(self) -> dict[str, str | int | None]:
        """Serialize to a dict for state marker storage."""
        return {
            "file": self.file,
            "line": self.line,
            "severity": self.severity,
            "message_hash": self.message_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FindingFingerprint:
        """Deserialize from a state marker dict."""
        return cls(
            file=data["file"],
            line=data["line"],
            severity=data["severity"],
            message_hash=data["message_hash"],
        )


def deduplicate_findings(
    new_findings: list[Finding],
    previous_fingerprints: list[FindingFingerprint],
) -> tuple[list[Finding], list[Finding]]:
    """Split new findings into (to_post, already_posted).

    A finding is 'already posted' if its fingerprint matches any previous
    fingerprint.  Otherwise it is 'to_post'.

    Returns:
        (to_post, already_posted) -- both lists contain Finding objects.
    """
    previous_set = set(previous_fingerprints)
    to_post: list[Finding] = []
    already_posted: list[Finding] = []

    for finding in new_findings:
        fp = FindingFingerprint.from_finding(finding)
        if fp in previous_set:
            already_posted.append(finding)
            _logger.debug(
                "Dedup: skipping duplicate finding file=%s line=%s",
                finding.file,
                finding.line,
            )
        else:
            to_post.append(finding)

    _logger.info(
        "Dedup: %d new findings to post, %d duplicates skipped",
        len(to_post),
        len(already_posted),
    )
    return to_post, already_posted


def build_inline_state(
    posted_findings: list[Finding],
    head_sha: str,
) -> dict[str, Any]:
    """Build the state dict entries for inline findings.

    Returns a dict with ``last_reviewed_sha`` and ``inline_findings``
    suitable for merging into the state marker.
    """
    return {
        "last_reviewed_sha": head_sha,
        "inline_findings": [FindingFingerprint.from_finding(f).to_dict() for f in posted_findings],
    }


def extract_previous_fingerprints(
    state: dict[str, Any] | None,
) -> list[FindingFingerprint]:
    """Extract FindingFingerprints from a previously stored state dict.

    Returns an empty list if *state* is ``None``, missing
    ``inline_findings``, or if ``inline_findings`` is malformed
    (graceful degradation -- no crash).
    """
    if state is None:
        return []

    raw = state.get("inline_findings")
    if not isinstance(raw, list):
        return []

    fingerprints: list[FindingFingerprint] = []
    for entry in raw:
        try:
            fingerprints.append(FindingFingerprint.from_dict(entry))
        except (KeyError, TypeError):
            _logger.debug("Skipping malformed fingerprint entry: %s", entry)
            continue

    return fingerprints
