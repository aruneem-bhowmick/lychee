"""Smoke, sanity, and regression tests for CI and development tooling configuration.

Validates that pyproject.toml tool sections, .pre-commit-config.yaml, and
.github/workflows/ci.yml are parseable, internally consistent, and match
golden snapshots for regression detection.
"""

import tomllib
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_pyproject() -> dict[str, Any]:
    """Load and return the parsed pyproject.toml."""
    with open(PROJECT_ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def _load_pre_commit() -> dict[str, Any]:
    """Load and return the parsed .pre-commit-config.yaml."""
    with open(PROJECT_ROOT / ".pre-commit-config.yaml") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
        return data


def _load_ci_workflow() -> dict[str, Any]:
    """Load and return the parsed .github/workflows/ci.yml."""
    with open(PROJECT_ROOT / ".github" / "workflows" / "ci.yml") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
        return data


# ---------------------------------------------------------------------------
# Smoke tests — configs are parseable
# ---------------------------------------------------------------------------


def test_pyproject_parseable() -> None:
    """pyproject.toml parses without error and contains tool sections."""
    data = _load_pyproject()
    assert "tool" in data
    assert "ruff" in data["tool"]
    assert "black" in data["tool"]
    assert "pytest" in data["tool"]
    assert "mypy" in data["tool"]
    assert "coverage" in data["tool"]


def test_pre_commit_valid_yaml() -> None:
    """.pre-commit-config.yaml parses as valid YAML with a repos key."""
    data = _load_pre_commit()
    assert "repos" in data
    assert isinstance(data["repos"], list)
    assert len(data["repos"]) > 0


def test_ci_workflow_valid_yaml() -> None:
    """.github/workflows/ci.yml parses as valid YAML with jobs key."""
    data = _load_ci_workflow()
    assert "jobs" in data
    assert isinstance(data["jobs"], dict)


# ---------------------------------------------------------------------------
# Sanity tests — values are consistent and sensible
# ---------------------------------------------------------------------------


def test_coverage_gate_at_least_one() -> None:
    """Coverage fail_under is at least 1 (non-trivial gate)."""
    data = _load_pyproject()
    fail_under = data["tool"]["coverage"]["report"]["fail_under"]
    assert fail_under >= 1


def test_hooks_pinned() -> None:
    """All pre-commit hooks have pinned rev values (not 'main' or 'latest')."""
    data = _load_pre_commit()
    for repo in data["repos"]:
        rev = repo.get("rev", "")
        assert rev not in ("main", "latest", "master", ""), (
            f"Hook {repo['repo']} has unpinned rev: {rev}"
        )


def test_ci_actions_pinned() -> None:
    """All CI workflow actions use pinned versions (@v4, @v5, etc.)."""
    data = _load_ci_workflow()
    for job_name, job in data["jobs"].items():
        for step in job.get("steps", []):
            uses = step.get("uses", "")
            if uses:
                assert "@" in uses, f"Action {uses} in job {job_name} is not pinned"


def test_all_tools_in_dev_deps() -> None:
    """All development tools are listed in pyproject.toml dev dependencies."""
    data = _load_pyproject()
    dev_deps = " ".join(data["project"]["optional-dependencies"]["dev"])
    for tool in ("pytest", "pytest-cov", "mypy", "ruff", "black", "pre-commit"):
        assert tool in dev_deps, f"{tool} missing from dev dependencies"


def test_line_length_consistent() -> None:
    """Ruff and black line-length settings match in pyproject.toml."""
    data = _load_pyproject()
    ruff_len = data["tool"]["ruff"]["line-length"]
    black_len = data["tool"]["black"]["line-length"]
    assert ruff_len == black_len, f"ruff ({ruff_len}) != black ({black_len})"


def test_ci_has_expected_jobs() -> None:
    """CI workflow defines lint, type-check, and test jobs."""
    data = _load_ci_workflow()
    for job in ("lint", "type-check", "test"):
        assert job in data["jobs"], f"Missing CI job: {job}"


def test_coverage_source_matches_package() -> None:
    """Coverage source path matches the package location."""
    data = _load_pyproject()
    sources = data["tool"]["coverage"]["run"]["source"]
    assert "src/lychee" in sources


def test_pytest_addopts_has_coverage() -> None:
    """pytest addopts includes --cov flags."""
    data = _load_pyproject()
    addopts = data["tool"]["pytest"]["ini_options"]["addopts"]
    assert "--cov=src/lychee" in addopts
    assert "--cov-fail-under" in addopts


# ---------------------------------------------------------------------------
# Regression snapshot tests
# ---------------------------------------------------------------------------


def test_pre_commit_config_snapshot() -> None:
    """.pre-commit-config.yaml matches the golden snapshot.

    On first run the snapshot is written automatically. Delete the snapshot
    file and re-run to regenerate after an intentional change.
    """
    current = (PROJECT_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    snapshot_path = FIXTURES_DIR / "pre_commit_config_snapshot.yaml"

    if not snapshot_path.exists():
        snapshot_path.write_text(current, encoding="utf-8")
        return

    saved = snapshot_path.read_text(encoding="utf-8")
    assert current == saved, (
        "Pre-commit config snapshot changed. If intentional, delete "
        "tests/fixtures/pre_commit_config_snapshot.yaml and re-run to regenerate."
    )


def test_ci_workflow_snapshot() -> None:
    """.github/workflows/ci.yml matches the golden snapshot.

    On first run the snapshot is written automatically. Delete the snapshot
    file and re-run to regenerate after an intentional change.
    """
    current = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    snapshot_path = FIXTURES_DIR / "ci_workflow_snapshot.yml"

    if not snapshot_path.exists():
        snapshot_path.write_text(current, encoding="utf-8")
        return

    saved = snapshot_path.read_text(encoding="utf-8")
    assert current == saved, (
        "CI workflow snapshot changed. If intentional, delete "
        "tests/fixtures/ci_workflow_snapshot.yml and re-run to regenerate."
    )
