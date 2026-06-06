"""Integration, system, smoke, acceptance, and e2e tests for the CLI dry-run path.

Verifies that `lychee review --dry-run --fixture <path>` runs the full
review pipeline end-to-end without any network I/O, renders a complete
PR comment to stdout, and exits 0.

Framework: pytest, click.testing.CliRunner, unittest.mock.patch.
Coverage target: >= 85% on src/lychee/review.py and src/lychee/__main__.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from lychee.__main__ import cli
from lychee.config import LycheeConfig
from lychee.render import REVIEW_MARKER
from lychee.review import run_review_dry

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PR_SIMPLE_FIXTURE = FIXTURES_DIR / "pr_simple.json"
REVIEW_RESULT_RIPE_FIXTURE = FIXTURES_DIR / "review_result_ripe.json"


@pytest.fixture
def default_config() -> LycheeConfig:
    """Default LycheeConfig with all fields at their documented defaults."""
    return LycheeConfig()


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_run_review_dry_returns_string(default_config: LycheeConfig) -> None:
    """run_review_dry returns a str for a valid pr_simple fixture."""
    result = run_review_dry(PR_SIMPLE_FIXTURE, default_config)
    assert isinstance(result, str)


def test_run_review_dry_output_contains_marker(default_config: LycheeConfig) -> None:
    """run_review_dry output contains the hidden lychee:review HTML marker."""
    result = run_review_dry(PR_SIMPLE_FIXTURE, default_config)
    assert REVIEW_MARKER in result


def test_run_review_dry_output_contains_nectar(default_config: LycheeConfig) -> None:
    """run_review_dry output contains the summary text from the ripe result fixture."""
    expected_summary = json.loads(REVIEW_RESULT_RIPE_FIXTURE.read_text(encoding="utf-8"))["summary"]

    result = run_review_dry(PR_SIMPLE_FIXTURE, default_config)

    assert expected_summary in result


def test_run_review_dry_missing_fixture_raises(default_config: LycheeConfig) -> None:
    """run_review_dry raises FileNotFoundError for a fixture path that does not exist."""
    with pytest.raises(FileNotFoundError):
        run_review_dry(Path("/nonexistent_lychee_fixture_path.json"), default_config)


def test_run_review_dry_invalid_json_raises(
    tmp_path: Path,
    default_config: LycheeConfig,
) -> None:
    """run_review_dry raises ValueError when the fixture file contains invalid JSON."""
    bad_fixture = tmp_path / "bad.json"
    bad_fixture.write_text("not valid json {{ garbage", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid fixture JSON"):
        run_review_dry(bad_fixture, default_config)


def test_run_review_dry_fallback_to_bundled_result(
    tmp_path: Path,
    default_config: LycheeConfig,
) -> None:
    """run_review_dry falls back to the bundled result fixture when no sidecar exists."""
    # Write a valid PR fixture to an isolated temp directory (no sidecar alongside it).
    isolated_fixture = tmp_path / "pr_isolated.json"
    isolated_fixture.write_text(PR_SIMPLE_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    # No review_result_ripe.json exists in tmp_path, so the fallback path is exercised.
    result = run_review_dry(isolated_fixture, default_config)

    assert REVIEW_MARKER in result
    assert "Reviewed to the core by Lychee" in result


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_cli_dry_run_invocation() -> None:
    """CLI dry-run exits 0 and prints the lychee:review marker."""
    runner = CliRunner()
    result = runner.invoke(cli, ["review", "--dry-run", "--fixture", str(PR_SIMPLE_FIXTURE)])
    assert result.exit_code == 0
    assert REVIEW_MARKER in result.output


def test_cli_dry_run_missing_fixture_flag() -> None:
    """CLI dry-run without --fixture exits non-zero and mentions --fixture in output."""
    runner = CliRunner()
    result = runner.invoke(cli, ["review", "--dry-run"])
    assert result.exit_code != 0
    assert "--fixture" in result.output


def test_cli_dry_run_full_sections() -> None:
    """CLI dry-run output contains Nectar and The Peel headings and the footer tag line."""
    runner = CliRunner()
    result = runner.invoke(cli, ["review", "--dry-run", "--fixture", str(PR_SIMPLE_FIXTURE)])
    assert result.exit_code == 0
    assert "Nectar" in result.output
    assert "The Peel" in result.output
    assert "Reviewed to the core by Lychee" in result.output


def test_cli_dry_run_nonexistent_fixture() -> None:
    """CLI rejects a --fixture path that does not exist with a non-zero exit code."""
    runner = CliRunner()
    result = runner.invoke(cli, ["review", "--dry-run", "--fixture", "/does/not/exist.json"])
    assert result.exit_code != 0


def test_cli_live_mode_not_available() -> None:
    """Invoking 'review' without --dry-run exits non-zero with an explanatory error."""
    runner = CliRunner()
    result = runner.invoke(cli, ["review"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# System tests
# ---------------------------------------------------------------------------


def test_dry_run_no_network_calls() -> None:
    """Dry-run makes zero network calls: patching socket.__init__ to raise never fires."""
    runner = CliRunner()
    with patch("socket.socket.__init__", side_effect=AssertionError("network call made")):
        result = runner.invoke(cli, ["review", "--dry-run", "--fixture", str(PR_SIMPLE_FIXTURE)])
    # If a socket were opened the AssertionError would propagate and set exit_code != 0.
    assert result.exit_code == 0


def test_dry_run_engine_full_flow(default_config: LycheeConfig) -> None:
    """run_review_dry returns a complete, non-empty comment with the ripe badge."""
    result = run_review_dry(PR_SIMPLE_FIXTURE, default_config)
    assert result  # non-empty string
    assert "🟢 **Ripe**" in result


def test_dry_run_deterministic(default_config: LycheeConfig) -> None:
    """run_review_dry produces identical output on two consecutive calls."""
    first = run_review_dry(PR_SIMPLE_FIXTURE, default_config)
    second = run_review_dry(PR_SIMPLE_FIXTURE, default_config)
    assert first == second


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_dry_run_prints_complete_comment() -> None:
    """Dry-run CLI output contains all five comment sections.

    Checks for Header (marker), Nectar, The Peel, Pits, and Footer.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["review", "--dry-run", "--fixture", str(PR_SIMPLE_FIXTURE)])
    assert result.exit_code == 0
    # Header
    assert REVIEW_MARKER in result.output
    # Nectar
    assert "Nectar" in result.output
    # The Peel
    assert "The Peel" in result.output
    # Pits
    assert "Pits" in result.output
    # Footer
    assert "Reviewed to the core by Lychee" in result.output


def test_accept_dry_run_exits_zero() -> None:
    """Dry-run CLI exits with code 0 on a successful run."""
    runner = CliRunner()
    result = runner.invoke(cli, ["review", "--dry-run", "--fixture", str(PR_SIMPLE_FIXTURE)])
    assert result.exit_code == 0


def test_accept_zero_network_calls() -> None:
    """Acceptance: no socket is opened during a dry-run CLI invocation."""
    runner = CliRunner()
    with patch("socket.socket.__init__", side_effect=AssertionError("network call made")):
        result = runner.invoke(cli, ["review", "--dry-run", "--fixture", str(PR_SIMPLE_FIXTURE)])
    assert result.exit_code == 0


def test_accept_output_contains_ripe_badge() -> None:
    """Acceptance: dry-run output contains the ripe ripeness badge from the fixture."""
    runner = CliRunner()
    result = runner.invoke(cli, ["review", "--dry-run", "--fixture", str(PR_SIMPLE_FIXTURE)])
    assert "🟢 **Ripe**" in result.output


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_cli_review_help() -> None:
    """'lychee review --help' exits 0 and documents the --dry-run flag."""
    runner = CliRunner()
    result = runner.invoke(cli, ["review", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output


def test_cli_group_help() -> None:
    """'lychee --help' exits 0."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0


def test_dry_run_imports() -> None:
    """All public names used by the dry-run path import cleanly."""
    from lychee.__main__ import cli
    from lychee.review import run_review_dry

    assert cli and run_review_dry


# ---------------------------------------------------------------------------
# End-to-end tests (excluded from the default run; invoke with -m e2e)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_e2e_dry_run_local() -> None:
    """E2E: dry-run via subprocess exits 0 and prints a complete review comment."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "lychee",
            "review",
            "--dry-run",
            "--fixture",
            str(PR_SIMPLE_FIXTURE),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"PYTHONUTF8": "1", **__import__("os").environ},
    )
    assert proc.returncode == 0
    assert REVIEW_MARKER in proc.stdout
    assert "Reviewed to the core by Lychee" in proc.stdout
