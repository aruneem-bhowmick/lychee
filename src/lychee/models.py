"""Domain types for Lychee review results (Findings, Ripeness, etc.)."""

from __future__ import annotations

from enum import Enum
from typing import Any

import pydantic


class Severity(str, Enum):
    """Severity level of a Finding (Pit)."""

    info = "info"
    minor = "minor"
    major = "major"
    critical = "critical"


class Ripeness(str, Enum):
    """Merge-readiness verdict for a PR."""

    ripe = "ripe"
    unripe = "unripe"
    sour = "sour"


class Category(str, Enum):
    """Classification of a Finding (Pit)."""

    correctness = "correctness"
    security = "security"
    performance = "performance"
    tests = "tests"
    style = "style"
    docs = "docs"
    other = "other"


class Finding(pydantic.BaseModel):
    """A single review finding (a Pit / Seed).

    `line` is None when the finding applies to the whole file.
    `suggestion` is None when no concrete fix is provided.
    """

    file: str
    line: int | None
    severity: Severity
    category: Category
    message: str
    suggestion: str | None


class ReviewResult(pydantic.BaseModel):
    """The structured output of a Lychee review produced by the submit_review tool call."""

    ripeness: Ripeness
    summary: str
    walkthrough: str
    findings: list[Finding]
    model: str
    usage: dict[str, Any]

    @classmethod
    def from_tool_input(cls, data: dict[str, Any]) -> ReviewResult:
        """Parse a submit_review tool-call input dict into a ReviewResult."""
        raise NotImplementedError("ReviewResult.from_tool_input not implemented")

    @classmethod
    def to_tool_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema dict for the submit_review Claude tool definition."""
        raise NotImplementedError("ReviewResult.to_tool_schema not implemented")
