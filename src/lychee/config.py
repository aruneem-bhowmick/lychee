"""Configuration loading and validation for Lychee.

Reads `.lychee.yml` from a given path (or the current working directory),
validates the contents against a strict schema, and returns an immutable
`LycheeConfig` object with all missing keys filled from documented defaults.

Unknown keys at any nesting level are rejected with a descriptive error.
All secrets come from environment variables — no secret fields are accepted here.
"""

from __future__ import annotations

import fnmatch
import logging
from pathlib import Path
from typing import Any, Literal

import pydantic
import yaml

_logger = logging.getLogger(__name__)


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


class ScopeRule(pydantic.BaseModel):
    """Per-path or per-label override for review behavior.

    Each rule can match files by glob pattern and/or PR labels, then
    override model selection, severity threshold, tone, or skip matched
    files entirely. Rules are evaluated in declaration order; first match wins.
    """

    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")

    paths: list[str] = pydantic.Field(default_factory=list)
    """Glob patterns matching file paths (relative to repo root). Empty = match all."""

    labels: list[str] = pydantic.Field(default_factory=list)
    """PR label names. Empty = match all."""

    model: str | None = None
    """Override the review model for matching files. None = use default."""

    severity_threshold: Literal["info", "minor", "major", "critical"] | None = None
    """Override severity threshold. None = use default."""

    tone: Literal["balanced", "concise", "detailed"] | None = None
    """Override tone. None = use default."""

    ignore: bool = False
    """If true, skip matching files entirely (exclude from review context)."""


class AuthorizationConfig(pydantic.BaseModel):
    """Authorization settings for command invocation.

    Controls which GitHub users are permitted to trigger @lychee commands.
    An empty ``allowed_users`` list means open access.
    """

    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")

    allowed_users: list[str] = pydantic.Field(default_factory=list)
    """GitHub logins allowed to trigger commands. Empty = open access."""


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
    budget_cap_usd: float | None = None
    scope_rules: list[ScopeRule] = pydantic.Field(default_factory=list)

    @pydantic.field_validator("language")
    @classmethod
    def language_must_be_nonempty(cls, v: str) -> str:
        """Reject empty-string language values; any non-empty string is accepted."""
        if not v:
            raise ValueError("language must be a non-empty string")
        return v

    @pydantic.field_validator("budget_cap_usd")
    @classmethod
    def budget_cap_must_be_positive(cls, v: float | None) -> float | None:
        """Reject non-positive budget cap values; None means no cap."""
        if v is not None and v <= 0:
            raise ValueError("budget_cap_usd must be > 0 when provided")
        return v


class FeaturesConfig(pydantic.BaseModel):
    """Feature flags that toggle optional review capabilities."""

    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")

    inline_comments: bool = False
    cost_footer: bool = True
    commands: bool = False
    triage_pass: bool = False


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
    authorization: AuthorizationConfig = pydantic.Field(default_factory=AuthorizationConfig)


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
        raise LycheeConfigError(f"Cannot read .lychee.yml at {resolved}: {exc}") from exc

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


def _rule_matches_file(rule: ScopeRule, file_path: str) -> bool:
    """Return True if the rule's path patterns match the given file path.

    An empty ``rule.paths`` list matches all files.
    """
    if not rule.paths:
        return True
    return any(fnmatch.fnmatch(file_path, pat) for pat in rule.paths)


def _rule_matches_labels(rule: ScopeRule, pr_labels: list[str]) -> bool:
    """Return True if the rule's label list matches the given PR labels.

    An empty ``rule.labels`` list matches all PRs regardless of labels.
    """
    if not rule.labels:
        return True
    return any(label in pr_labels for label in rule.labels)


def should_ignore_file(
    file_path: str,
    scope_rules: list[ScopeRule],
    pr_labels: list[str],
) -> bool:
    """Return True if *file_path* should be excluded from the review context.

    Iterates scope rules in declaration order. The first rule whose path
    globs and label list both match determines the outcome. If that rule
    has ``ignore=True``, the file is excluded; otherwise it is kept.

    If no rule matches, the file is kept (not ignored).
    """
    for rule in scope_rules:
        if _rule_matches_file(rule, file_path) and _rule_matches_labels(rule, pr_labels):
            if rule.ignore:
                _logger.debug(
                    "Scope rule ignoring file %s (paths=%s, labels=%s)",
                    file_path,
                    rule.paths,
                    rule.labels,
                )
                return True
            return False
    return False


def resolve_scope_overrides(
    config: LycheeConfig,
    file_paths: list[str],
    pr_labels: list[str],
) -> dict[str, Any]:
    """Resolve effective config overrides from scope rules.

    Iterates scope rules in declaration order. For each file path, the first
    rule whose path globs and label list both match wins. Returns a dict of
    override keys (``model``, ``severity_threshold``, ``tone``) with values
    from the winning rule. Keys not overridden by any matching rule are absent.

    When multiple files match different rules, the first file's matching rule
    takes precedence (the override applies to the entire review run).

    If no rule matches any file, returns an empty dict (use global defaults).
    """
    scope_rules = config.review.scope_rules
    if not scope_rules:
        return {}

    for file_path in file_paths:
        for rule in scope_rules:
            if _rule_matches_file(rule, file_path) and _rule_matches_labels(rule, pr_labels):
                overrides: dict[str, Any] = {}
                if rule.model is not None:
                    overrides["model"] = rule.model
                if rule.severity_threshold is not None:
                    overrides["severity_threshold"] = rule.severity_threshold
                if rule.tone is not None:
                    overrides["tone"] = rule.tone
                if overrides:
                    _logger.debug(
                        "Scope rule matched file %s: overrides=%s",
                        file_path,
                        overrides,
                    )
                return overrides

    return {}
