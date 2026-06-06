"""Domain types for Lychee review results (Findings, Ripeness, etc.)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import pydantic


class Severity(StrEnum):
    """Severity level of a Finding (Pit)."""

    info = "info"
    minor = "minor"
    major = "major"
    critical = "critical"


class Ripeness(StrEnum):
    """Merge-readiness verdict for a PR."""

    ripe = "ripe"
    unripe = "unripe"
    sour = "sour"


class Category(StrEnum):
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

    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")

    file: str
    line: int | None = None
    severity: Severity
    category: Category
    message: str
    suggestion: str | None = None

    @pydantic.field_validator("suggestion")
    @classmethod
    def suggestion_must_be_nonempty(cls, v: str | None) -> str | None:
        """Reject empty-string suggestions; use None for absent suggestions."""
        if v is not None and v == "":
            raise ValueError("suggestion must be non-empty if provided; use None instead")
        return v


class ReviewResult(pydantic.BaseModel):
    """The structured output of a Lychee review (produced by `submit_review` tool call).

    `usage` mirrors the Anthropic SDK InputCostTokens / OutputCostTokens dict verbatim
    for cost tracking downstream.
    """

    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")

    ripeness: Ripeness
    summary: str  # the Nectar
    walkthrough: str  # the Peel (markdown)
    findings: list[Finding]  # the Pits
    model: str
    usage: dict[str, Any]

    @pydantic.field_validator("summary", "walkthrough", "model")
    @classmethod
    def must_be_nonempty(cls, v: str) -> str:
        """Reject empty strings for required text fields."""
        if not v:
            raise ValueError("field must be non-empty")
        return v

    @classmethod
    def from_tool_input(cls, data: dict[str, Any]) -> ReviewResult:
        """Parse a `submit_review` tool-call input dict into a ReviewResult.

        Raises pydantic.ValidationError on malformed or missing fields.
        """
        return cls.model_validate(data)

    @classmethod
    def to_tool_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema dict for the `submit_review` Claude tool definition.

        The schema is derived from the Pydantic model's JSON schema and conforms
        to the Anthropic tool-use format with a top-level `name` and `description`.
        """
        return {
            "name": "submit_review",
            "description": "Submit a structured PR review result.",
            "input_schema": cls.model_json_schema(),
        }
