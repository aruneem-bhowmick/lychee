"""Tests for scope rule matching, override resolution, and ignore filtering.

Covers ScopeRule and AuthorizationConfig model defaults, validation,
resolve_scope_overrides() logic, and should_ignore_file() behavior
including glob matching, label matching, first-match-wins semantics,
and edge cases.

Framework: pytest.  Coverage target: >= 90% on scope-rule logic.
"""

from __future__ import annotations

from pathlib import Path

import pydantic
import pytest

from lychee.config import (
    AuthorizationConfig,
    LycheeConfig,
    ReviewConfig,
    ScopeRule,
    load_config,
    resolve_scope_overrides,
    should_ignore_file,
)

# ---------------------------------------------------------------------------
# Unit tests -- ScopeRule model defaults and validation
# ---------------------------------------------------------------------------


def test_scope_rule_defaults() -> None:
    """An empty ScopeRule() has paths=[], labels=[], all overrides None, ignore=False."""
    rule = ScopeRule()
    assert rule.paths == []
    assert rule.labels == []
    assert rule.model is None
    assert rule.severity_threshold is None
    assert rule.tone is None
    assert rule.ignore is False


def test_scope_rule_extra_key_rejected() -> None:
    """An unknown key on ScopeRule raises a ValidationError."""
    with pytest.raises(pydantic.ValidationError):
        ScopeRule(unknown_field="oops")  # type: ignore[call-arg]


def test_scope_rule_invalid_severity() -> None:
    """An invalid severity_threshold string is rejected by the Literal type."""
    with pytest.raises(pydantic.ValidationError):
        ScopeRule(severity_threshold="blocker")  # type: ignore[arg-type]


def test_scope_rule_invalid_tone() -> None:
    """An invalid tone string is rejected by the Literal type."""
    with pytest.raises(pydantic.ValidationError):
        ScopeRule(tone="aggressive")  # type: ignore[arg-type]


def test_scope_rule_frozen() -> None:
    """ScopeRule instances are immutable."""
    rule = ScopeRule()
    with pytest.raises(pydantic.ValidationError):
        rule.ignore = True  # type: ignore[misc]


def test_scope_rule_valid_severity_values() -> None:
    """All four valid severity_threshold values are accepted."""
    for level in ("info", "minor", "major", "critical"):
        rule = ScopeRule(severity_threshold=level)  # type: ignore[arg-type]
        assert rule.severity_threshold == level


def test_scope_rule_valid_tone_values() -> None:
    """All three valid tone values are accepted."""
    for tone in ("balanced", "concise", "detailed"):
        rule = ScopeRule(tone=tone)  # type: ignore[arg-type]
        assert rule.tone == tone


# ---------------------------------------------------------------------------
# Unit tests -- AuthorizationConfig defaults and validation
# ---------------------------------------------------------------------------


def test_authorization_config_defaults() -> None:
    """AuthorizationConfig() has allowed_users=[]."""
    auth = AuthorizationConfig()
    assert auth.allowed_users == []


def test_authorization_config_with_users() -> None:
    """AuthorizationConfig parses a list of usernames correctly."""
    auth = AuthorizationConfig(allowed_users=["alice", "bob"])
    assert auth.allowed_users == ["alice", "bob"]


def test_authorization_config_extra_key_rejected() -> None:
    """An unknown key on AuthorizationConfig raises a ValidationError."""
    with pytest.raises(pydantic.ValidationError):
        AuthorizationConfig(roles=["admin"])  # type: ignore[call-arg]


def test_authorization_config_frozen() -> None:
    """AuthorizationConfig instances are immutable."""
    auth = AuthorizationConfig(allowed_users=["alice"])
    with pytest.raises(pydantic.ValidationError):
        auth.allowed_users = []  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Unit tests -- should_ignore_file()
# ---------------------------------------------------------------------------


def test_should_ignore_file_matching() -> None:
    """A file matching an ignore=True rule returns True."""
    rules = [ScopeRule(paths=["*.lock"], ignore=True)]
    assert should_ignore_file("yarn.lock", rules, []) is True
    assert should_ignore_file("package.json", rules, []) is False
    assert should_ignore_file("src/main.py", rules, []) is False


def test_should_ignore_file_no_match() -> None:
    """A file not matching any rule returns False."""
    rules = [ScopeRule(paths=["tests/**"], ignore=True)]
    assert should_ignore_file("src/main.py", rules, []) is False


def test_should_ignore_file_label_required() -> None:
    """A rule with labels only matches when the PR has that label."""
    rules = [ScopeRule(labels=["security"], ignore=True)]

    # Without the label, all files are kept
    assert should_ignore_file("src/main.py", rules, []) is False
    assert should_ignore_file("src/main.py", rules, ["bugfix"]) is False

    # With the label, all files are ignored (empty paths = match all)
    assert should_ignore_file("src/main.py", rules, ["security"]) is True


def test_should_ignore_file_path_and_label_required() -> None:
    """Both path and label must match for a combined rule."""
    rules = [ScopeRule(paths=["generated/**"], labels=["autogen"], ignore=True)]

    # Only path matches
    assert should_ignore_file("generated/output.py", rules, []) is False
    # Only label matches
    assert should_ignore_file("src/main.py", rules, ["autogen"]) is False
    # Both match
    assert should_ignore_file("generated/output.py", rules, ["autogen"]) is True


def test_should_ignore_file_non_ignore_rule_stops_search() -> None:
    """A matching rule without ignore=True prevents later ignore rules from firing."""
    rules = [
        ScopeRule(paths=["src/**"], model="claude-opus-4-8"),  # matches first, ignore=False
        ScopeRule(paths=["src/**"], ignore=True),  # would match but is never reached
    ]
    assert should_ignore_file("src/core/engine.py", rules, []) is False


def test_should_ignore_file_empty_rules() -> None:
    """No rules means no files are ignored."""
    assert should_ignore_file("anything.py", [], []) is False


def test_should_ignore_file_glob_patterns() -> None:
    """Glob patterns work for nested paths."""
    rules = [ScopeRule(paths=["docs/**", "*.md"], ignore=True)]
    assert should_ignore_file("docs/guide.md", rules, []) is True
    assert should_ignore_file("README.md", rules, []) is True
    assert should_ignore_file("src/docs.py", rules, []) is False


# ---------------------------------------------------------------------------
# Unit tests -- resolve_scope_overrides()
# ---------------------------------------------------------------------------


def test_resolve_overrides_first_match() -> None:
    """The first matching rule's overrides are returned; later rules are ignored."""
    config = LycheeConfig(
        review=ReviewConfig(
            scope_rules=[
                ScopeRule(paths=["src/**"], model="claude-opus-4-8", tone="detailed"),
                ScopeRule(paths=["src/**"], model="claude-haiku-4-5-20251001"),
            ]
        )
    )
    overrides = resolve_scope_overrides(config, ["src/app.py"], [])
    assert overrides["model"] == "claude-opus-4-8"
    assert overrides["tone"] == "detailed"


def test_resolve_overrides_no_match() -> None:
    """No matching rule returns an empty dict."""
    config = LycheeConfig(
        review=ReviewConfig(
            scope_rules=[ScopeRule(paths=["tests/**"], model="claude-opus-4-8")]
        )
    )
    overrides = resolve_scope_overrides(config, ["src/app.py"], [])
    assert overrides == {}


def test_resolve_overrides_partial() -> None:
    """A rule with only model set returns only {'model': ...}."""
    config = LycheeConfig(
        review=ReviewConfig(
            scope_rules=[ScopeRule(paths=["src/**"], model="claude-opus-4-8")]
        )
    )
    overrides = resolve_scope_overrides(config, ["src/app.py"], [])
    assert overrides == {"model": "claude-opus-4-8"}
    assert "severity_threshold" not in overrides
    assert "tone" not in overrides


def test_resolve_overrides_path_glob() -> None:
    """paths: ['src/core/**'] matches src/core/engine.py."""
    config = LycheeConfig(
        review=ReviewConfig(
            scope_rules=[
                ScopeRule(paths=["src/core/**"], severity_threshold="critical")
            ]
        )
    )
    overrides = resolve_scope_overrides(config, ["src/core/engine.py"], [])
    assert overrides == {"severity_threshold": "critical"}


def test_resolve_overrides_label_match() -> None:
    """labels: ['security'] matches when PR label list includes 'security'."""
    config = LycheeConfig(
        review=ReviewConfig(
            scope_rules=[
                ScopeRule(
                    labels=["security"],
                    severity_threshold="critical",
                    tone="detailed",
                )
            ]
        )
    )
    overrides = resolve_scope_overrides(config, ["src/app.py"], ["security"])
    assert overrides["severity_threshold"] == "critical"
    assert overrides["tone"] == "detailed"


def test_resolve_overrides_label_no_match() -> None:
    """A label-based rule returns empty dict when labels do not match."""
    config = LycheeConfig(
        review=ReviewConfig(
            scope_rules=[
                ScopeRule(labels=["security"], severity_threshold="critical")
            ]
        )
    )
    overrides = resolve_scope_overrides(config, ["src/app.py"], ["bugfix"])
    assert overrides == {}


def test_resolve_overrides_no_scope_rules() -> None:
    """A config with no scope_rules returns an empty dict."""
    config = LycheeConfig()
    overrides = resolve_scope_overrides(config, ["src/app.py"], [])
    assert overrides == {}


def test_resolve_overrides_empty_file_paths() -> None:
    """Empty file_paths list returns empty dict even with rules defined."""
    config = LycheeConfig(
        review=ReviewConfig(
            scope_rules=[ScopeRule(paths=["src/**"], model="claude-opus-4-8")]
        )
    )
    overrides = resolve_scope_overrides(config, [], [])
    assert overrides == {}


def test_resolve_overrides_all_fields() -> None:
    """A rule with all override fields set returns all three keys."""
    config = LycheeConfig(
        review=ReviewConfig(
            scope_rules=[
                ScopeRule(
                    model="claude-opus-4-8",
                    severity_threshold="major",
                    tone="concise",
                )
            ]
        )
    )
    overrides = resolve_scope_overrides(config, ["any_file.py"], [])
    assert overrides == {
        "model": "claude-opus-4-8",
        "severity_threshold": "major",
        "tone": "concise",
    }


def test_resolve_overrides_ignore_rule_returns_empty() -> None:
    """An ignore rule matches but has no model/threshold/tone overrides to return."""
    config = LycheeConfig(
        review=ReviewConfig(
            scope_rules=[ScopeRule(paths=["generated/**"], ignore=True)]
        )
    )
    overrides = resolve_scope_overrides(config, ["generated/out.py"], [])
    assert overrides == {}


# ---------------------------------------------------------------------------
# Integration tests -- config loading with scope rules
# ---------------------------------------------------------------------------


def test_config_with_scope_rules_parses(tmp_path: Path) -> None:
    """A YAML with review.scope_rules loads correctly."""
    cfg = tmp_path / ".lychee.yml"
    cfg.write_text(
        "review:\n"
        "  scope_rules:\n"
        "    - paths:\n"
        "        - 'src/core/**'\n"
        "      model: claude-opus-4-8\n"
        "      severity_threshold: critical\n",
        encoding="utf-8",
    )
    config = load_config(cfg)
    assert len(config.review.scope_rules) == 1
    rule = config.review.scope_rules[0]
    assert rule.paths == ["src/core/**"]
    assert rule.model == "claude-opus-4-8"
    assert rule.severity_threshold == "critical"
    assert rule.tone is None
    assert rule.ignore is False


def test_config_with_authorization_parses(tmp_path: Path) -> None:
    """A YAML with authorization.allowed_users loads correctly."""
    cfg = tmp_path / ".lychee.yml"
    cfg.write_text(
        "authorization:\n"
        "  allowed_users:\n"
        "    - admin-user\n"
        "    - deploy-bot\n",
        encoding="utf-8",
    )
    config = load_config(cfg)
    assert config.authorization.allowed_users == ["admin-user", "deploy-bot"]


def test_existing_config_still_loads(tmp_path: Path) -> None:
    """A YAML without scope_rules or authorization loads (backward compatibility)."""
    cfg = tmp_path / ".lychee.yml"
    cfg.write_text(
        "model:\n  default: claude-sonnet-4-6\nreview:\n  max_files: 30\n",
        encoding="utf-8",
    )
    config = load_config(cfg)
    assert config.model.default == "claude-sonnet-4-6"
    assert config.review.max_files == 30
    assert config.review.scope_rules == []
    assert config.authorization.allowed_users == []


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_load_config_defaults_include_new_fields() -> None:
    """load_config() default includes empty scope_rules and default authorization."""
    config = LycheeConfig()
    assert config.review.scope_rules == []
    assert config.authorization == AuthorizationConfig()
    assert config.authorization.allowed_users == []


def test_existing_config_tests_pass() -> None:
    """Verify the ScopeRule and AuthorizationConfig can coexist with all existing fields."""
    config = LycheeConfig()
    assert config.model is not None
    assert config.review is not None
    assert config.features is not None
    assert config.authorization is not None
    assert config.conventions_file is None


# ---------------------------------------------------------------------------
# Regression tests -- parametrized scope rule matching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "file_path", "pr_labels", "expected_ignore"),
    [
        # Empty rule matches everything, but ignore=False by default
        (ScopeRule(), "any.py", [], False),
        # Path glob match with ignore
        (ScopeRule(paths=["*.lock"], ignore=True), "yarn.lock", [], True),
        # Path glob no match
        (ScopeRule(paths=["*.lock"], ignore=True), "src/app.py", [], False),
        # Label match with ignore
        (ScopeRule(labels=["skip"], ignore=True), "any.py", ["skip"], True),
        # Label no match
        (ScopeRule(labels=["skip"], ignore=True), "any.py", ["review"], False),
        # Both path and label required -- both match
        (ScopeRule(paths=["gen/**"], labels=["auto"], ignore=True), "gen/out.py", ["auto"], True),
        # Both required -- only path matches
        (ScopeRule(paths=["gen/**"], labels=["auto"], ignore=True), "gen/out.py", [], False),
        # Both required -- only label matches
        (ScopeRule(paths=["gen/**"], labels=["auto"], ignore=True), "src/a.py", ["auto"], False),
        # Nested glob
        (ScopeRule(paths=["src/core/**"], ignore=True), "src/core/deep/file.py", [], True),
        # Non-ignore rule
        (ScopeRule(paths=["src/**"], model="claude-opus-4-8"), "src/app.py", [], False),
    ],
    ids=[
        "empty_rule_no_ignore",
        "path_glob_match_ignore",
        "path_glob_no_match",
        "label_match_ignore",
        "label_no_match",
        "path_and_label_both_match",
        "path_and_label_only_path",
        "path_and_label_only_label",
        "nested_glob_match",
        "non_ignore_rule",
    ],
)
def test_scope_rule_matching_snapshot(
    rule: ScopeRule,
    file_path: str,
    pr_labels: list[str],
    expected_ignore: bool,
) -> None:
    """Parametrized fixture locking scope rule matching edge cases."""
    result = should_ignore_file(file_path, [rule], pr_labels)
    assert result is expected_ignore


def test_config_round_trip_with_scope_rules() -> None:
    """A config with scope rules serializes and deserializes losslessly."""
    original = LycheeConfig(
        review=ReviewConfig(
            scope_rules=[
                ScopeRule(
                    paths=["src/core/**"],
                    model="claude-opus-4-8",
                    severity_threshold="critical",
                ),
                ScopeRule(
                    labels=["generated"],
                    ignore=True,
                ),
            ]
        ),
        authorization=AuthorizationConfig(allowed_users=["admin"]),
    )
    dumped = original.model_dump()
    restored = LycheeConfig.model_validate(dumped)
    assert restored == original
    assert restored.review.scope_rules == original.review.scope_rules
    assert restored.authorization.allowed_users == original.authorization.allowed_users


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_path_rules_change_scope() -> None:
    """Files matching a path rule's ignore=True are excluded by should_ignore_file."""
    rules = [
        ScopeRule(paths=["generated/**", "*.auto.py"], ignore=True),
        ScopeRule(paths=["src/**"], model="claude-opus-4-8"),
    ]
    assert should_ignore_file("generated/output.py", rules, []) is True
    assert should_ignore_file("build.auto.py", rules, []) is True
    assert should_ignore_file("src/main.py", rules, []) is False


def test_accept_label_rules_change_model() -> None:
    """A label-based rule overrides the model selection."""
    config = LycheeConfig(
        review=ReviewConfig(
            scope_rules=[
                ScopeRule(
                    labels=["security"],
                    model="claude-opus-4-8",
                    severity_threshold="critical",
                )
            ]
        )
    )
    overrides = resolve_scope_overrides(config, ["src/auth.py"], ["security"])
    assert overrides["model"] == "claude-opus-4-8"
    assert overrides["severity_threshold"] == "critical"

    # Without the label, no override
    no_overrides = resolve_scope_overrides(config, ["src/auth.py"], [])
    assert no_overrides == {}
