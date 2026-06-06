"""Scaffold tests: verify package structure, imports, and CLI entry point."""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner


# ---------------------------------------------------------------------------
# Smoke tests — all modules must import without raising
# ---------------------------------------------------------------------------


def test_all_modules_import() -> None:
    """All lychee modules import cleanly with no side-effects or errors."""  # P0-R1
    import lychee  # noqa: F401
    import lychee.models  # noqa: F401
    import lychee.config  # noqa: F401
    import lychee.github_client  # noqa: F401
    import lychee.context  # noqa: F401
    import lychee.prompt  # noqa: F401
    import lychee.claude  # noqa: F401
    import lychee.render  # noqa: F401
    import lychee.review  # noqa: F401
    import lychee.poster  # noqa: F401


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_version_string() -> None:
    """Package exposes __version__ equal to '0.1.0'."""  # P0-R1
    import lychee

    assert lychee.__version__ == "0.1.0"


def test_module_signatures_models() -> None:
    """lychee.models exposes the expected public names."""  # P0-R1
    import lychee.models as m

    for name in ("Severity", "Ripeness", "Category", "Finding", "ReviewResult"):
        assert hasattr(m, name), f"lychee.models is missing '{name}'"


def test_module_signatures_config() -> None:
    """lychee.config exposes LycheeConfig and load_config."""  # P0-R1
    import lychee.config as m

    assert hasattr(m, "LycheeConfig")
    assert hasattr(m, "load_config")
    assert callable(m.load_config)


def test_module_signatures_github_client() -> None:
    """lychee.github_client exposes GitHubClient."""  # P0-R1
    import lychee.github_client as m

    assert hasattr(m, "GitHubClient")


def test_module_signatures_context() -> None:
    """lychee.context exposes ReviewContext and build_context."""  # P0-R1
    import lychee.context as m

    assert hasattr(m, "ReviewContext")
    assert hasattr(m, "build_context")
    assert callable(m.build_context)


def test_module_signatures_prompt() -> None:
    """lychee.prompt exposes build_messages."""  # P0-R1
    import lychee.prompt as m

    assert hasattr(m, "build_messages")
    assert callable(m.build_messages)


def test_module_signatures_claude() -> None:
    """lychee.claude exposes ClaudeClient."""  # P0-R1
    import lychee.claude as m

    assert hasattr(m, "ClaudeClient")


def test_module_signatures_render() -> None:
    """lychee.render exposes render_comment."""  # P0-R1
    import lychee.render as m

    assert hasattr(m, "render_comment")
    assert callable(m.render_comment)


def test_module_signatures_review() -> None:
    """lychee.review exposes run_review."""  # P0-R1
    import lychee.review as m

    assert hasattr(m, "run_review")
    assert callable(m.run_review)


def test_module_signatures_poster() -> None:
    """lychee.poster exposes SummaryPoster."""  # P0-R1
    import lychee.poster as m

    assert hasattr(m, "SummaryPoster")


# ---------------------------------------------------------------------------
# Acceptance tests — CLI behaviour via CliRunner
# ---------------------------------------------------------------------------


def test_cli_help() -> None:
    """'lychee --help' exits 0 and mentions 'lychee' in the output."""  # P0-R1
    from lychee.__main__ import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "lychee" in result.output.lower()


def test_review_subcommand_help() -> None:
    """'lychee review --help' lists --dry-run and --fixture options."""  # P0-R1
    from lychee.__main__ import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["review", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output
    assert "--fixture" in result.output


def test_review_subcommand_is_registered() -> None:
    """The 'review' subcommand appears in the main --help listing."""  # P0-R1
    from lychee.__main__ import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "review" in result.output


# ---------------------------------------------------------------------------
# Sanity tests — entry point wired via subprocess
# ---------------------------------------------------------------------------


def test_entry_point_wired() -> None:
    """'python -m lychee --help' exits 0, confirming the entry point is wired."""  # P0-R1
    result = subprocess.run(
        [sys.executable, "-m", "lychee", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ---------------------------------------------------------------------------
# Regression tests — pyproject.toml structural integrity
# ---------------------------------------------------------------------------


def test_pyproject_has_required_keys() -> None:
    """pyproject.toml contains all required packaging and entry-point keys."""  # P0-R1
    root = Path(__file__).parent.parent
    with open(root / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)

    assert data["project"]["name"] == "lychee"
    assert "lychee" in data["project"]["scripts"]
    assert data["project"]["scripts"]["lychee"] == "lychee.__main__:cli"
    assert data["build-system"]["build-backend"] == "hatchling.build"


def test_pyproject_requires_python() -> None:
    """pyproject.toml declares requires-python >= 3.11."""  # P0-R1
    root = Path(__file__).parent.parent
    with open(root / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)

    requires = data["project"]["requires-python"]
    assert "3.11" in requires


def test_pyproject_has_runtime_dependencies() -> None:
    """pyproject.toml lists all required runtime dependencies."""  # P0-R1
    root = Path(__file__).parent.parent
    with open(root / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)

    deps = " ".join(data["project"]["dependencies"])
    for pkg in ("anthropic", "PyGithub", "PyYAML", "pydantic", "click", "httpx"):
        assert pkg in deps, f"Expected '{pkg}' in dependencies"


# ---------------------------------------------------------------------------
# Regression tests — .lychee.yml structural integrity
# ---------------------------------------------------------------------------


def test_lychee_yml_has_required_sections() -> None:
    """Default .lychee.yml contains model, review, and features sections."""  # P0-R1
    import yaml

    root = Path(__file__).parent.parent
    with open(root / ".lychee.yml") as fh:
        cfg = yaml.safe_load(fh)

    assert "model" in cfg
    assert "review" in cfg
    assert "features" in cfg


def test_lychee_yml_model_keys() -> None:
    """Default .lychee.yml defines model.default, model.triage, and model.large_pr."""  # P0-R1
    import yaml

    root = Path(__file__).parent.parent
    with open(root / ".lychee.yml") as fh:
        cfg = yaml.safe_load(fh)

    model = cfg["model"]
    assert "default" in model
    assert "triage" in model
    assert "large_pr" in model


def test_lychee_yml_review_keys() -> None:
    """Default .lychee.yml defines all expected review sub-keys."""  # P0-R1
    import yaml

    root = Path(__file__).parent.parent
    with open(root / ".lychee.yml") as fh:
        cfg = yaml.safe_load(fh)

    review = cfg["review"]
    for key in (
        "ignore_globs",
        "max_files",
        "max_file_bytes",
        "severity_threshold",
        "tone",
        "language",
    ):
        assert key in review, f"review.{key} missing from .lychee.yml"


def test_lychee_yml_features_keys() -> None:
    """Default .lychee.yml defines features.inline_comments, cost_footer, and commands."""  # P0-R1
    import yaml

    root = Path(__file__).parent.parent
    with open(root / ".lychee.yml") as fh:
        cfg = yaml.safe_load(fh)

    features = cfg["features"]
    for key in ("inline_comments", "cost_footer", "commands"):
        assert key in features, f"features.{key} missing from .lychee.yml"


# ---------------------------------------------------------------------------
# Unit tests — enum members (populated after CodeRabbit feedback)
# ---------------------------------------------------------------------------


def test_severity_members() -> None:
    """Severity enum has exactly the four expected string members."""  # P0-R1
    from lychee.models import Severity

    assert Severity.info.value == "info"
    assert Severity.minor.value == "minor"
    assert Severity.major.value == "major"
    assert Severity.critical.value == "critical"
    assert len(Severity) == 4


def test_ripeness_members() -> None:
    """Ripeness enum has exactly the three expected string members."""  # P0-R1
    from lychee.models import Ripeness

    assert Ripeness.ripe.value == "ripe"
    assert Ripeness.unripe.value == "unripe"
    assert Ripeness.sour.value == "sour"
    assert len(Ripeness) == 3


def test_category_members() -> None:
    """Category enum has exactly the seven expected string members."""  # P0-R1
    from lychee.models import Category

    expected = {"correctness", "security", "performance", "tests", "style", "docs", "other"}
    assert {m.value for m in Category} == expected


def test_severity_is_str_enum() -> None:
    """Severity members compare equal to their raw string values."""  # P0-R1
    from lychee.models import Severity

    assert Severity.critical == "critical"
    assert Severity.info == "info"


def test_to_tool_schema_is_classmethod() -> None:
    """ReviewResult.to_tool_schema is accessible as a classmethod without an instance."""  # P0-R1
    import inspect

    from lychee.models import ReviewResult

    assert isinstance(inspect.getattr_static(ReviewResult, "to_tool_schema"), classmethod)


# ---------------------------------------------------------------------------
# Unit tests — fail-fast behavior on unimplemented stubs
# ---------------------------------------------------------------------------


def test_load_config_returns_lychee_config() -> None:
    """load_config() returns a LycheeConfig instance rather than raising."""
    from lychee.config import LycheeConfig, load_config

    result = load_config()
    assert isinstance(result, LycheeConfig)


def test_build_context_raises_not_implemented() -> None:
    """build_context raises NotImplementedError rather than silently returning None."""  # P0-R1
    from lychee.context import build_context

    with pytest.raises(NotImplementedError, match="build_context"):
        build_context(object(), "owner/repo#1", object())


def test_render_comment_raises_not_implemented() -> None:
    """render_comment raises NotImplementedError rather than silently returning None."""  # P0-R1
    from lychee.models import Finding, Ripeness, ReviewResult, Severity, Category
    from lychee.render import render_comment

    result = ReviewResult(
        ripeness=Ripeness.ripe,
        summary="ok",
        walkthrough="lgtm",
        findings=[],
        model="claude-sonnet-4-6",
        usage={},
    )
    with pytest.raises(NotImplementedError, match="render_comment"):
        render_comment(result)



def test_summary_poster_post_raises_not_implemented() -> None:
    """SummaryPoster.post raises NotImplementedError rather than silently no-oping."""  # P0-R1
    from lychee.poster import SummaryPoster

    poster = SummaryPoster(github_client=object())
    with pytest.raises(NotImplementedError, match="SummaryPoster.post"):
        poster.post("owner/repo#1", "body")


# ---------------------------------------------------------------------------
# Acceptance tests — CLI error path
# ---------------------------------------------------------------------------


def test_review_command_exits_cleanly_when_unimplemented() -> None:
    """Running 'lychee review' exits with a formatted error, no Python traceback."""  # P0-R1
    from lychee.__main__ import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["review"])

    assert result.exit_code != 0
    # Click converts ClickException to SystemExit — no unhandled exception escaped.
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "Traceback" not in (result.output or "")
    assert "not yet implemented" in result.output
