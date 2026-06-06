"""Domain types for Lychee review results (Findings, Ripeness, etc.)."""

from __future__ import annotations

from enum import Enum
from typing import Any

import pydantic


class Severity(str, Enum):
    """Severity level of a Finding (Pit)."""

    ...


class Ripeness(str, Enum):
    """Merge-readiness verdict for a PR."""

    ...


class Category(str, Enum):
    """Classification of a Finding (Pit)."""

    ...


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
        ...

    def to_tool_schema(self) -> dict[str, Any]:
        """Return the JSON Schema dict for the submit_review Claude tool definition."""
        ...
