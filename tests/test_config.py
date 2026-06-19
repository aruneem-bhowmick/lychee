"""Unit, smoke, sanity, regression, and acceptance tests for lychee.config.

Covers the full behaviour of `load_config` and the Pydantic config models:
default values, file-absent handling, unknown-key rejection, malformed-YAML
errors, type violations, enum constraints, immutability, and snapshot
regression checks.

Framework: pytest.  Coverage target: ≥ 90% on src/lychee/config.py.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pydantic
import pytest

from lychee.config import (
    AuthorizationConfig,
    FeaturesConfig,
    LycheeConfig,
    LycheeConfigError,
    ModelConfig,
    ReviewConfig,
    ScopeRule,
    load_config,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_config_module_imports() -> None:
    """All public names import cleanly from lychee.config."""
    from lychee.config import (
        AuthorizationConfig,
        FeaturesConfig,
        LycheeConfig,
        LycheeConfigError,
        ModelConfig,
        ReviewConfig,
        ScopeRule,
        load_config,
    )

    assert all(
        [
            LycheeConfig,
            LycheeConfigError,
            load_config,
            ModelConfig,
            ReviewConfig,
            FeaturesConfig,
            ScopeRule,
            AuthorizationConfig,
        ]
    )


# ---------------------------------------------------------------------------
# Unit tests — defaults and file loading
# ---------------------------------------------------------------------------


def test_load_empty_file_returns_defaults() -> None:
    """An empty YAML file produces a config with every documented default value."""
    config = load_config(FIXTURES_DIR / "lychee_defaults.yml")

    assert config.model.default == "claude-sonnet-4-6"
    assert config.model.triage == "claude-haiku-4-5-20251001"
    assert config.model.large_pr == "claude-opus-4-8"
    assert config.review.ignore_globs == []
    assert config.review.max_files == 50
    assert config.review.max_file_bytes == 102_400
    assert config.review.severity_threshold == "info"
    assert config.review.tone == "balanced"
    assert config.review.language == "en"
    assert config.review.scope_rules == []
    assert config.features.inline_comments is False
    assert config.features.cost_footer is True
    assert config.features.commands is False
    assert config.conventions_file is None
    assert config.authorization.allowed_users == []


def test_load_absent_file_returns_defaults() -> None:
    """Pointing at a path that does not exist returns a default LycheeConfig without error."""
    config = load_config(Path("/nonexistent/.lychee.yml"))

    assert isinstance(config, LycheeConfig)
    assert config.review.max_files == 50
    assert config.model.default == "claude-sonnet-4-6"


def test_load_valid_config_overrides_defaults() -> None:
    """A fully-populated valid config file overrides all default values correctly."""
    config = load_config(FIXTURES_DIR / "lychee_valid.yml")

    assert config.model.default == "claude-opus-4-8"
    assert config.model.triage == "claude-sonnet-4-6"
    assert config.review.max_files == 25
    assert config.review.max_file_bytes == 51_200
    assert config.review.severity_threshold == "major"
    assert config.review.tone == "concise"
    assert config.review.language == "fr"
    assert config.review.ignore_globs == ["*.lock", "dist/**"]
    assert config.features.inline_comments is True
    assert config.features.cost_footer is False
    assert config.features.commands is True
    assert config.conventions_file == "CONVENTIONS.md"
    assert len(config.review.scope_rules) == 2
    assert config.review.scope_rules[0].paths == ["src/core/**"]
    assert config.review.scope_rules[0].model == "claude-opus-4-8"
    assert config.review.scope_rules[1].labels == ["generated"]
    assert config.review.scope_rules[1].ignore is True
    assert config.authorization.allowed_users == ["admin-user", "bot-user"]


def test_defaults_applied_for_omitted_keys(tmp_path: Path) -> None:
    """A partial config receives documented defaults for every omitted key."""
    partial = tmp_path / ".lychee.yml"
    partial.write_text("model:\n  default: claude-opus-4-8\n", encoding="utf-8")

    config = load_config(partial)

    assert config.model.default == "claude-opus-4-8"
    # All other keys should fall back to defaults.
    assert config.model.triage == "claude-haiku-4-5-20251001"
    assert config.review.max_files == 50
    assert config.features.cost_footer is True
    assert config.conventions_file is None


# ---------------------------------------------------------------------------
# Unit tests — error cases
# ---------------------------------------------------------------------------


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    """A top-level unknown key raises LycheeConfigError with 'unknown' in the message."""
    bad = tmp_path / ".lychee.yml"
    bad.write_text("foo: bar\n", encoding="utf-8")

    with pytest.raises(LycheeConfigError, match=r"[Uu]nknown"):
        load_config(bad)


def test_unknown_nested_key_rejected() -> None:
    """An unknown key inside a nested section raises LycheeConfigError."""
    with pytest.raises(LycheeConfigError):
        load_config(FIXTURES_DIR / "lychee_unknown_key.yml")


def test_malformed_yaml_raises(tmp_path: Path) -> None:
    """Syntactically invalid YAML raises LycheeConfigError with 'Malformed' in the message."""
    bad = tmp_path / ".lychee.yml"
    bad.write_text("key: :\n", encoding="utf-8")

    with pytest.raises(LycheeConfigError, match="Malformed"):
        load_config(bad)


def test_permission_error_raises(tmp_path: Path) -> None:
    """A file that exists but raises OSError on read produces LycheeConfigError."""
    cfg = tmp_path / ".lychee.yml"
    cfg.write_text("model:\n  default: test\n", encoding="utf-8")

    with (
        patch.object(Path, "read_text", side_effect=OSError("Permission denied")),
        pytest.raises(LycheeConfigError, match="Cannot read"),
    ):
        load_config(cfg)


def test_encoding_error_raises(tmp_path: Path) -> None:
    """A file containing non-UTF-8 bytes raises LycheeConfigError on read."""
    cfg = tmp_path / ".lychee.yml"
    cfg.write_bytes(b"\xff\xfe\x00 not valid utf-8")

    with pytest.raises(LycheeConfigError, match="Cannot read"):
        load_config(cfg)


def test_invalid_max_files_type_raises(tmp_path: Path) -> None:
    """A non-integer max_files value raises LycheeConfigError."""
    bad = tmp_path / ".lychee.yml"
    bad.write_text("review:\n  max_files: fifty\n", encoding="utf-8")

    with pytest.raises(LycheeConfigError):
        load_config(bad)


def test_invalid_severity_threshold_raises(tmp_path: Path) -> None:
    """An unrecognized severity_threshold value raises LycheeConfigError."""
    bad = tmp_path / ".lychee.yml"
    bad.write_text("review:\n  severity_threshold: blocker\n", encoding="utf-8")

    with pytest.raises(LycheeConfigError):
        load_config(bad)


def test_invalid_tone_raises(tmp_path: Path) -> None:
    """An unrecognized tone value raises LycheeConfigError."""
    bad = tmp_path / ".lychee.yml"
    bad.write_text("review:\n  tone: aggressive\n", encoding="utf-8")

    with pytest.raises(LycheeConfigError):
        load_config(bad)


def test_empty_language_raises(tmp_path: Path) -> None:
    """An empty-string language value raises LycheeConfigError."""
    bad = tmp_path / ".lychee.yml"
    bad.write_text("review:\n  language: ''\n", encoding="utf-8")

    with pytest.raises(LycheeConfigError):
        load_config(bad)


def test_invalid_max_file_bytes_type_raises(tmp_path: Path) -> None:
    """A non-integer max_file_bytes value raises LycheeConfigError."""
    bad = tmp_path / ".lychee.yml"
    bad.write_text("review:\n  max_file_bytes: large\n", encoding="utf-8")

    with pytest.raises(LycheeConfigError):
        load_config(bad)


def test_unknown_features_key_rejected(tmp_path: Path) -> None:
    """An unknown key inside the features section raises LycheeConfigError."""
    bad = tmp_path / ".lychee.yml"
    bad.write_text("features:\n  turbo_mode: true\n", encoding="utf-8")

    with pytest.raises(LycheeConfigError, match=r"[Uu]nknown"):
        load_config(bad)


def test_unknown_model_key_rejected(tmp_path: Path) -> None:
    """An unknown key inside the model section raises LycheeConfigError."""
    bad = tmp_path / ".lychee.yml"
    bad.write_text("model:\n  experimental: gpt-9\n", encoding="utf-8")

    with pytest.raises(LycheeConfigError, match=r"[Uu]nknown"):
        load_config(bad)


def test_invalid_inline_comments_type_raises(tmp_path: Path) -> None:
    """A non-boolean inline_comments value raises LycheeConfigError."""
    bad = tmp_path / ".lychee.yml"
    bad.write_text("features:\n  inline_comments: maybe\n", encoding="utf-8")

    with pytest.raises(LycheeConfigError):
        load_config(bad)


# ---------------------------------------------------------------------------
# Unit tests — specific field and model defaults
# ---------------------------------------------------------------------------


def test_config_is_frozen() -> None:
    """Attempting to mutate any config field raises a Pydantic ValidationError."""
    config = LycheeConfig()
    with pytest.raises(pydantic.ValidationError):
        config.review.max_files = 1  # type: ignore[misc]


def test_top_level_config_is_frozen() -> None:
    """Attempting to set a top-level field raises a Pydantic ValidationError."""
    config = LycheeConfig()
    with pytest.raises(pydantic.ValidationError):
        config.conventions_file = "NEW.md"  # type: ignore[misc]


def test_conventions_file_none_by_default() -> None:
    """conventions_file is None when the key is absent from the config."""
    config = load_config(FIXTURES_DIR / "lychee_defaults.yml")
    assert config.conventions_file is None


def test_conventions_file_set() -> None:
    """conventions_file is loaded correctly when specified in the config file."""
    config = load_config(FIXTURES_DIR / "lychee_valid.yml")
    assert config.conventions_file == "CONVENTIONS.md"


def test_model_defaults() -> None:
    """ModelConfig constructed with no arguments has the correct default model strings."""
    config = LycheeConfig()
    assert config.model.default == "claude-sonnet-4-6"
    assert config.model.triage == "claude-haiku-4-5-20251001"
    assert config.model.large_pr == "claude-opus-4-8"


def test_features_defaults() -> None:
    """FeaturesConfig constructed with no arguments has the correct default flag states."""
    config = LycheeConfig()
    assert config.features.inline_comments is False
    assert config.features.cost_footer is True
    assert config.features.commands is False


def test_review_all_severity_thresholds_accepted(tmp_path: Path) -> None:
    """All four documented severity_threshold values are accepted without error."""
    for level in ("info", "minor", "major", "critical"):
        cfg = tmp_path / f".lychee_{level}.yml"
        cfg.write_text(f"review:\n  severity_threshold: {level}\n", encoding="utf-8")
        result = load_config(cfg)
        assert result.review.severity_threshold == level


def test_review_all_tones_accepted(tmp_path: Path) -> None:
    """All three documented tone values are accepted without error."""
    for tone in ("balanced", "concise", "detailed"):
        cfg = tmp_path / f".lychee_{tone}.yml"
        cfg.write_text(f"review:\n  tone: {tone}\n", encoding="utf-8")
        result = load_config(cfg)
        assert result.review.tone == tone


def test_ignore_globs_list_loaded(tmp_path: Path) -> None:
    """A non-empty ignore_globs list is loaded as a list of strings."""
    cfg = tmp_path / ".lychee.yml"
    cfg.write_text(
        "review:\n  ignore_globs:\n    - '*.lock'\n    - 'node_modules/**'\n",
        encoding="utf-8",
    )
    result = load_config(cfg)
    assert result.review.ignore_globs == ["*.lock", "node_modules/**"]


def test_model_config_has_correct_sub_model_types() -> None:
    """LycheeConfig sub-configs are instances of their respective model classes."""
    config = LycheeConfig()
    assert isinstance(config.model, ModelConfig)
    assert isinstance(config.review, ReviewConfig)
    assert isinstance(config.features, FeaturesConfig)
    assert isinstance(config.authorization, AuthorizationConfig)


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_all_defaults_present() -> None:
    """Every field of a default LycheeConfig is non-None except conventions_file."""
    config = LycheeConfig()
    assert config.model is not None
    assert config.review is not None
    assert config.features is not None
    assert config.conventions_file is None  # None by design


def test_load_config_no_args_does_not_crash() -> None:
    """Calling load_config() with no arguments returns a LycheeConfig without raising."""
    config = load_config()
    assert isinstance(config, LycheeConfig)


# ---------------------------------------------------------------------------
# Regression snapshot tests
# ---------------------------------------------------------------------------


def test_config_defaults_snapshot() -> None:
    """Default LycheeConfig serialization matches the golden snapshot.

    On first run the snapshot is written automatically.  Delete the snapshot
    file and re-run to regenerate after an intentional schema change.
    """
    config = LycheeConfig()
    serialized = json.dumps(config.model_dump(), sort_keys=True, indent=2)

    snapshot_path = FIXTURES_DIR / "config_defaults_snapshot.json"
    if not snapshot_path.exists():
        snapshot_path.write_text(serialized, encoding="utf-8")
        return

    saved = snapshot_path.read_text(encoding="utf-8")
    assert serialized == saved, (
        "Default config snapshot changed. If intentional, delete "
        "tests/fixtures/config_defaults_snapshot.json and re-run to regenerate."
    )


def test_valid_config_snapshot() -> None:
    """Valid config file serialization matches the golden snapshot.

    On first run the snapshot is written automatically.  Delete the snapshot
    file and re-run to regenerate after an intentional schema or fixture change.
    """
    config = load_config(FIXTURES_DIR / "lychee_valid.yml")
    serialized = json.dumps(config.model_dump(), sort_keys=True, indent=2)

    snapshot_path = FIXTURES_DIR / "config_valid_snapshot.json"
    if not snapshot_path.exists():
        snapshot_path.write_text(serialized, encoding="utf-8")
        return

    saved = snapshot_path.read_text(encoding="utf-8")
    assert serialized == saved, (
        "Valid config snapshot changed. If intentional, delete "
        "tests/fixtures/config_valid_snapshot.json and re-run to regenerate."
    )


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_valid_file_loads_with_defaults(tmp_path: Path) -> None:
    """Given a valid partial .lychee.yml, load_config returns a config with all
    missing keys filled from documented defaults."""
    cfg = tmp_path / ".lychee.yml"
    cfg.write_text("review:\n  max_files: 10\n", encoding="utf-8")

    config = load_config(cfg)
    assert config.review.max_files == 10
    assert config.review.tone == "balanced"
    assert config.model.default == "claude-sonnet-4-6"
    assert config.features.cost_footer is True


def test_accept_unknown_key_error_top_level(tmp_path: Path) -> None:
    """Given a file with an unknown top-level key, load_config raises a clear error
    naming the bad key."""
    bad = tmp_path / ".lychee.yml"
    bad.write_text("forbidden_key: value\n", encoding="utf-8")

    with pytest.raises(LycheeConfigError) as exc_info:
        load_config(bad)

    assert "forbidden_key" in str(exc_info.value)


def test_accept_unknown_key_error_nested() -> None:
    """Given a file with an unknown nested key, load_config raises a LycheeConfigError."""
    with pytest.raises(LycheeConfigError):
        load_config(FIXTURES_DIR / "lychee_unknown_key.yml")


def test_accept_defaults_documented_and_tested() -> None:
    """Every documented default is present on a zero-argument LycheeConfig."""
    config = LycheeConfig()

    # Model defaults
    assert config.model.default == "claude-sonnet-4-6"
    assert config.model.triage == "claude-haiku-4-5-20251001"
    assert config.model.large_pr == "claude-opus-4-8"

    # Review defaults
    assert config.review.ignore_globs == []
    assert config.review.max_files == 50
    assert config.review.max_file_bytes == 102_400
    assert config.review.severity_threshold == "info"
    assert config.review.tone == "balanced"
    assert config.review.language == "en"
    assert config.review.scope_rules == []

    # Feature defaults
    assert config.features.inline_comments is False
    assert config.features.cost_footer is True
    assert config.features.commands is False

    # Top-level defaults
    assert config.conventions_file is None
    assert config.authorization.allowed_users == []
