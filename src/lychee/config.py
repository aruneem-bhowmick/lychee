"""Configuration loading and validation for Lychee.

Reads `.lychee.yml` from a given path (or the current working directory),
validates the contents against a strict schema, and returns an immutable
`LycheeConfig` object with all missing keys filled from documented defaults.

Unknown keys at any nesting level are rejected with a descriptive error.
All secrets come from environment variables — no secret fields are accepted here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import pydantic
import yaml


class LycheeConfigError(Exception):
    """Raised when `.lychee.yml` contains invalid or unknown configuration."""


class ModelConfig(pydantic.BaseModel):
    """Model selection per review type.

    Controls which Claude model is used for each review scenario.
    All fields default to the current recommended model identifiers.
    """

    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")

    default: str = "claude-sonnet-4-6"
    triage: str = "claude-haiku-4-5-20251001"
    large_pr: str = "claude-opus-4-8"


class ReviewConfig(pydantic.BaseModel):
    """Review behavior settings.

    Controls file filtering, size limits, and output style for each review.
    """

    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")

    ignore_globs: list[str] = pydantic.Field(default_factory=list)
    max_files: int = 50
    max_file_bytes: int = 102_400  # 100 KiB per file
    severity_threshold: Literal["info", "minor", "major", "critical"] = "info"
    tone: Literal["balanced", "concise", "detailed"] = "balanced"
    language: str = "en"

    @pydantic.field_validator("language")
    @classmethod
    def language_must_be_nonempty(cls, v: str) -> str:
        """Reject empty-string language values; any non-empty string is accepted."""
        if not v:
            raise ValueError("language must be a non-empty string")
        return v


class FeaturesConfig(pydantic.BaseModel):
    """Feature flags that toggle optional review capabilities."""

    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")

    inline_comments: bool = False
    cost_footer: bool = True
    commands: bool = False


class LycheeConfig(pydantic.BaseModel):
    """Top-level validated configuration object.

    Produced by `load_config()`; immutable after construction.
    All sub-configs are themselves frozen Pydantic models — no field on any
    nested object can be mutated after construction.
    """

    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")

    model: ModelConfig = pydantic.Field(default_factory=ModelConfig)
    review: ReviewConfig = pydantic.Field(default_factory=ReviewConfig)
    features: FeaturesConfig = pydantic.Field(default_factory=FeaturesConfig)
    conventions_file: str | None = None


def _format_validation_error(e: pydantic.ValidationError, path: Path | None) -> str:
    """Translate a Pydantic ValidationError into a human-readable config error message.

    Produces one line per Pydantic error entry. Extra/unknown keys are reported
    with the prefix "Unknown config key:"; literal-type mismatches include the
    set of valid choices; all other type violations include the field path and
    the Pydantic message.
    """
    file_ref = f" in {path}" if path else ""
    messages: list[str] = []
    for error in e.errors():
        loc = ".".join(str(part) for part in error["loc"])
        err_type = error["type"]
        msg = error["msg"]
        if err_type == "extra_forbidden":
            messages.append(f"Unknown config key: {loc}")
        elif err_type == "literal_error":
            expected = error.get("ctx", {}).get("expected", "")
            messages.append(
                f"Invalid .lychee.yml{file_ref} — invalid value for {loc}: {msg}. "
                f"Valid values are: {expected}."
            )
        else:
            messages.append(f"Invalid .lychee.yml{file_ref} — {loc}: {msg}.")
    return "\n".join(messages)


def load_config(path: Path | None = None) -> LycheeConfig:
    """Load and validate `.lychee.yml` from `path`.

    Resolution order:
    - If `path` is provided, that exact path is used.
    - If `path` is None, the loader checks `<cwd>/.lychee.yml`.
    - If the resolved file does not exist, all-defaults `LycheeConfig` is returned.

    Raises `LycheeConfigError` when:
    - The file exists but cannot be read (permission denied, encoding error, I/O failure).
    - The YAML is syntactically malformed.
    - An unknown key appears at any nesting level.
    - A field value fails type or constraint validation (e.g. wrong type, bad enum).

    The returned object is fully immutable; no field may be set after construction.
    """
    resolved = path if path is not None else Path.cwd() / ".lychee.yml"

    if not resolved.exists():
        return LycheeConfig()

    try:
        raw_text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise LycheeConfigError(
            f"Cannot read .lychee.yml at {resolved}: {exc}"
        ) from exc

    try:
        raw: dict[str, Any] | None = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise LycheeConfigError(f"Malformed .lychee.yml: {exc}") from exc

    if raw is None:
        raw = {}

    try:
        return LycheeConfig.model_validate(raw)
    except pydantic.ValidationError as exc:
        raise LycheeConfigError(_format_validation_error(exc, resolved)) from exc
