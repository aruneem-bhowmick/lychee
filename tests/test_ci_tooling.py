"""Smoke, sanity, and regression tests for CI and tooling configuration files.

Validates that pyproject.toml, .pre-commit-config.yaml, and
.github/workflows/ci.yml are structurally correct, internally consistent,
and unchanged relative to their golden snapshots.  No Python logic is
exercised here; the tests confirm configuration correctness so that tooling
regressions (accidental pin upgrades, missing sections, broken YAML) are
caught before they reach CI.

Framework: pytest.  Uses tomllib (stdlib in 3.11) for TOML and yaml.safe_load
for YAML; no mocking is required.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
PYPROJECT = ROOT / "pyproject.toml"
PRECOMMIT = ROOT / ".pre-commit-config.yaml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_toml() -> dict:  # type: ignore[type-arg]
    """Return the parsed contents of pyproject.toml."""
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def _load_precommit() -> dict:  # type: ignore[type-arg]
    """Return the parsed contents of .pre-commit-config.yaml."""
    return yaml.safe_load(PRECOMMIT.read_text(encoding="utf-8"))  # type: ignore[return-value]


def _load_ci() -> dict:  # type: ignore[type-arg]
    """Return the parsed contents of .github/workflows/ci.yml."""
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Smoke tests — config files are parseable and contain expected sections
# ---------------------------------------------------------------------------


def test_ruff_config_parseable() -> None:
    """pyproject.toml [tool.ruff] section exists and lint.select contains required rules."""
    data = _load_toml()
    ruff = data["tool"]["ruff"]
    assert ruff, "[tool.ruff] section is missing or empty"
    lint_select = ruff["lint"]["select"]
    for rule in ("E", "F", "I"):
        assert rule in lint_select, f"ruff lint.select is missing rule '{rule}'"


def test_black_config_parseable() -> None:
    """pyproject.toml [tool.black] section exists and line-length is 100."""
    data = _load_toml()
    black = data["tool"]["black"]
    assert black, "[tool.black] section is missing or empty"
    assert black["line-length"] == 100, f"Expected line-length=100, got {black['line-length']}"


def test_pytest_config_parseable() -> None:
    """pyproject.toml [tool.pytest.ini_options] exists and testpaths is ['tests']."""
    data = _load_toml()
    pytest_opts = data["tool"]["pytest"]["ini_options"]
    assert pytest_opts, "[tool.pytest.ini_options] section is missing or empty"
    assert pytest_opts["testpaths"] == [
        "tests"
    ], f"Expected testpaths=['tests'], got {pytest_opts['testpaths']}"


def test_coverage_config_parseable() -> None:
    """pyproject.toml [tool.coverage.report] exists and contains fail_under."""
    data = _load_toml()
    report = data["tool"]["coverage"]["report"]
    assert report, "[tool.coverage.report] section is missing or empty"
    assert "fail_under" in report, "[tool.coverage.report] is missing fail_under"


def test_precommit_config_valid_yaml() -> None:
    """[.pre-commit-config.yaml] loads as valid YAML and repos is a list."""
    data = _load_precommit()
    assert data is not None, ".pre-commit-config.yaml is empty or null"
    assert isinstance(data["repos"], list), "'repos' in .pre-commit-config.yaml must be a list"
    assert len(data["repos"]) > 0, "'repos' list in .pre-commit-config.yaml is empty"


def test_ci_workflow_valid_yaml() -> None:
    """[.github/workflows/ci.yml] loads as valid YAML with lint, type-check, and test jobs."""
    data = _load_ci()
    assert data is not None, "ci.yml is empty or null"
    jobs = data["jobs"]
    for expected_job in ("lint", "type-check", "test"):
        assert expected_job in jobs, f"ci.yml is missing the '{expected_job}' job"


# ---------------------------------------------------------------------------
# Sanity tests — internal consistency of configuration values
# ---------------------------------------------------------------------------


def test_coverage_gate_configured() -> None:
    """fail_under in [tool.coverage.report] is a positive integer (gate is active)."""
    data = _load_toml()
    fail_under = data["tool"]["coverage"]["report"]["fail_under"]
    assert isinstance(fail_under, int), f"fail_under must be an integer, got {type(fail_under)}"
    assert fail_under >= 1, f"Coverage gate fail_under must be >= 1, got {fail_under}"


def test_precommit_hooks_pinned() -> None:
    """Every repo in .pre-commit-config.yaml has a pinned rev (not 'HEAD' or 'latest')."""
    data = _load_precommit()
    for repo in data["repos"]:
        url = repo.get("repo", "<unknown>")
        rev = repo.get("rev", "")
        assert rev, f"pre-commit repo '{url}' is missing a 'rev' field"
        assert rev not in (
            "HEAD",
            "latest",
        ), f"pre-commit repo '{url}' is pinned to '{rev}' instead of a fixed version tag"


def test_ci_actions_pinned() -> None:
    """Every 'uses:' step in ci.yml is pinned to a @vN tag, not @main or @master."""
    data = _load_ci()
    for job_name, job in data["jobs"].items():
        for step in job.get("steps", []):
            uses = step.get("uses", "")
            if not uses:
                continue
            assert (
                "@main" not in uses and "@master" not in uses
            ), f"Step '{uses}' in job '{job_name}' is pinned to a branch, not a version tag"
            assert re.search(
                r"@v\d", uses
            ), f"Step '{uses}' in job '{job_name}' is not pinned to a @vN tag"


def test_all_tools_in_dev_deps() -> None:
    """pytest, mypy, ruff, and black all appear in [project.optional-dependencies.dev]."""
    data = _load_toml()
    dev_deps = " ".join(data["project"]["optional-dependencies"]["dev"])
    for tool in ("pytest", "mypy", "ruff", "black"):
        assert tool in dev_deps, f"'{tool}' is missing from [project.optional-dependencies.dev]"


# ---------------------------------------------------------------------------
# Regression / snapshot tests — detect accidental pin or content changes
# ---------------------------------------------------------------------------


def test_precommit_config_snapshot() -> None:
    """[.pre-commit-config.yaml] content matches the golden snapshot.

    The snapshot guards against accidental hook-version upgrades or structural
    changes to the pre-commit config.  To update intentionally: delete
    tests/fixtures/precommit_config_snapshot.txt and re-run to regenerate.
    """
    snapshot_path = FIXTURES / "precommit_config_snapshot.txt"
    if not snapshot_path.exists():
        snapshot_path.write_text(PRECOMMIT.read_text(encoding="utf-8"), encoding="utf-8")
        pytest.skip("Snapshot did not exist — written on this run; re-run to compare.")
    actual = PRECOMMIT.read_text(encoding="utf-8")
    expected = snapshot_path.read_text(encoding="utf-8")
    assert actual == expected, (
        ".pre-commit-config.yaml differs from snapshot. "
        "If the change is intentional, delete tests/fixtures/precommit_config_snapshot.txt "
        "and re-run to regenerate."
    )


def test_ci_workflow_snapshot() -> None:
    """[.github/workflows/ci.yml] content matches the golden snapshot.

    Guards against accidental job additions, removals, or action-version
    changes.  To update intentionally: delete
    tests/fixtures/ci_workflow_snapshot.yml and re-run to regenerate.
    """
    snapshot_path = FIXTURES / "ci_workflow_snapshot.yml"
    if not snapshot_path.exists():
        snapshot_path.write_text(CI_WORKFLOW.read_text(encoding="utf-8"), encoding="utf-8")
        pytest.skip("Snapshot did not exist — written on this run; re-run to compare.")
    actual = CI_WORKFLOW.read_text(encoding="utf-8")
    expected = snapshot_path.read_text(encoding="utf-8")
    assert actual == expected, (
        ".github/workflows/ci.yml differs from snapshot. "
        "If the change is intentional, delete tests/fixtures/ci_workflow_snapshot.yml "
        "and re-run to regenerate."
    )


# ---------------------------------------------------------------------------
# Acceptance — CI as the primary gate (documented, not executable in pytest)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Acceptance criterion is the live CI run, not a local pytest assertion.")
def test_accept_ci_passes_clean_checkout() -> None:
    """CI passes on every push to main and every PR targeting main.

    This test is the primary acceptance criterion for the tooling setup.  It
    cannot be asserted inside pytest because it requires a full GitHub Actions
    runner; the live CI run (lint → type-check → test) is the executable form.
    The snapshot and sanity tests in this module are the closest local proxy.
    """
