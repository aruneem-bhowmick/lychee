"""Comprehensive tests verifying that engine modules are unchanged.

Ensures the core review engine modules (those that transform a PR into a
posted review) have not been modified.  Provides hash-based verification,
public API surface checks, and import graph validation to guard against
accidental engine drift between the Action and App code paths.

Framework: pytest.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SRC_DIR: Path = Path(__file__).parent.parent / "src" / "lychee"
_FIXTURES_DIR: Path = Path(__file__).parent / "fixtures"

# Engine modules whose source files MUST NOT be modified.
# config.py and observability.py are excluded because they were
# legitimately extended (AppConfig, server metrics).
_STRICT_ENGINE_MODULES: list[str] = [
    "models.py",
    "context.py",
    "prompt.py",
    "claude.py",
    "review.py",
    "render.py",
    "poster.py",
    "diff_mapping.py",
    "inline_render.py",
    "dedup.py",
    "cost.py",
    "rate_limiter.py",
    "triage.py",
    "commands.py",
    "authorization.py",
    "command_render.py",
]

# All engine modules (including extended ones) for API checks.
_ALL_ENGINE_MODULE_NAMES: list[str] = [
    "lychee.models",
    "lychee.config",
    "lychee.context",
    "lychee.prompt",
    "lychee.claude",
    "lychee.review",
    "lychee.render",
    "lychee.poster",
    "lychee.diff_mapping",
    "lychee.inline_render",
    "lychee.dedup",
    "lychee.cost",
    "lychee.rate_limiter",
    "lychee.triage",
    "lychee.observability",
    "lychee.commands",
    "lychee.authorization",
    "lychee.command_render",
]

# Legacy hash for review.py (kept for backward compatibility with
# existing tests).
_EXPECTED_REVIEW_SHA256 = "00a845e881314f70389067fa922008f59140073f2dc5bb2387a3ab5cfb7bf20c"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json_fixture(name: str) -> Any:
    """Load and parse a JSON fixture file from the fixtures directory."""
    path = _FIXTURES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def _compute_file_hash(file_path: Path) -> str:
    """Compute the SHA-256 hash of a file with LF-normalized content."""
    content = file_path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def _get_module_public_api(module_name: str) -> list[str]:
    """Import a module and return its public API names (sorted).

    Uses ``__all__`` if defined, otherwise falls back to ``dir()``
    filtered to exclude private names (those starting with ``_``).
    """
    mod = importlib.import_module(module_name)
    all_attr = getattr(mod, "__all__", None)
    if all_attr is not None:
        return sorted(all_attr)
    return sorted(n for n in dir(mod) if not n.startswith("_"))


# ============================================================================
# UNIT TESTS
# ============================================================================


def test_engine_module_list_complete() -> None:
    """Verify the engine module list covers all known engine modules.

    The list of strict engine modules used for hash checking must not
    omit any engine module file that exists in src/lychee/.
    """
    # P5-R6
    known_engine_files = set(_STRICT_ENGINE_MODULES)

    # Extended modules that are intentionally excluded from hash checks.
    extended_modules = {"config.py", "observability.py"}

    # Non-engine modules (infrastructure for App mode, not part of the
    # review engine pipeline).
    non_engine_modules = {
        "__init__.py",
        "__main__.py",
        "app_auth.py",
        "github_client.py",
        "health.py",
        "queue.py",
        "state_store.py",
        "webhook.py",
    }

    all_py_files = {f.name for f in _SRC_DIR.iterdir() if f.suffix == ".py"}

    # Every .py file should be accounted for in one of the three sets.
    expected_accounted = known_engine_files | extended_modules | non_engine_modules
    unaccounted = all_py_files - expected_accounted
    assert unaccounted == set(), (
        f"Unaccounted engine module files: {unaccounted}. " f"Add them to the appropriate category."
    )


def test_baseline_fixture_exists() -> None:
    """Verify engine baseline fixture files exist and contain valid JSON.

    Both ``engine_hashes_phase4.json`` and ``engine_api_phase4.json``
    must be present in ``tests/fixtures/`` and parse as valid JSON dicts.
    """
    # P5-R6
    hashes_path = _FIXTURES_DIR / "engine_hashes_phase4.json"
    api_path = _FIXTURES_DIR / "engine_api_phase4.json"

    assert hashes_path.exists(), f"Missing fixture: {hashes_path}"
    assert api_path.exists(), f"Missing fixture: {api_path}"

    hashes = json.loads(hashes_path.read_text(encoding="utf-8"))
    api = json.loads(api_path.read_text(encoding="utf-8"))

    assert isinstance(hashes, dict), "engine_hashes_phase4.json must be a JSON object"
    assert isinstance(api, dict), "engine_api_phase4.json must be a JSON object"
    assert len(hashes) > 0, "engine_hashes_phase4.json must not be empty"
    assert len(api) > 0, "engine_api_phase4.json must not be empty"


# ============================================================================
# HASH-BASED ENGINE INTEGRITY TESTS
# ============================================================================


def test_engine_modules_not_modified() -> None:
    """Verify engine module source files have not been modified.

    Computes a SHA-256 hash of each strict engine module's source file
    (with LF-normalized line endings) and compares against the recorded
    baseline.  If any hash differs, the test fails with a message naming
    the modified file(s).

    Extended modules (config.py, observability.py) are excluded because
    they were legitimately extended with App-mode functionality.
    """
    # P5-R6
    baseline: dict[str, str] = _load_json_fixture("engine_hashes_phase4.json")
    modified: list[str] = []

    for module_file in _STRICT_ENGINE_MODULES:
        expected_hash = baseline.get(module_file)
        if expected_hash is None:
            modified.append(f"{module_file} (no baseline hash recorded)")
            continue

        file_path = _SRC_DIR / module_file
        if not file_path.exists():
            modified.append(f"{module_file} (file missing)")
            continue

        actual_hash = _compute_file_hash(file_path)
        if actual_hash != expected_hash:
            modified.append(
                f"{module_file} (expected={expected_hash[:12]}..., "
                f"actual={actual_hash[:12]}...)"
            )

    assert modified == [], (
        f"Engine module(s) modified: {', '.join(modified)}. " f"The engine must not be modified."
    )


def test_engine_review_py_unchanged() -> None:
    """Verify review.py has not been modified by computing its SHA-256 hash.

    Legacy test retained for backward compatibility.  Uses the original
    single-file hash check approach.
    """
    # P5-R6
    review_path = _SRC_DIR / "review.py"
    content = review_path.read_bytes().replace(b"\r\n", b"\n")
    actual_hash = hashlib.sha256(content).hexdigest()
    assert actual_hash == _EXPECTED_REVIEW_SHA256, (
        f"review.py has been modified.\n"
        f"Expected SHA-256: {_EXPECTED_REVIEW_SHA256}\n"
        f"Actual SHA-256:   {actual_hash}\n"
        f"If this change is intentional, update _EXPECTED_REVIEW_SHA256 in "
        f"{__file__}."
    )


def test_engine_review_py_no_git_diff() -> None:
    """Verify review.py has no uncommitted or staged changes via git diff.

    Runs ``git diff HEAD -- src/lychee/review.py`` and asserts the output
    is empty, confirming no pending modifications exist.
    """
    # P5-R6
    review_path = _SRC_DIR / "review.py"
    result = subprocess.run(
        ["git", "diff", "HEAD", "--", str(review_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout == "", f"review.py has uncommitted changes:\n{result.stdout}"


# ============================================================================
# PUBLIC API SURFACE TESTS
# ============================================================================


def test_engine_public_api_unchanged() -> None:
    """Verify the public API of each engine module is unchanged.

    Imports each engine module and compares its public names against the
    recorded baseline.  New names are allowed (additive extensions);
    removed or renamed names cause a failure.  This ensures backward
    compatibility is preserved.
    """
    # P5-R6
    baseline: dict[str, list[str]] = _load_json_fixture("engine_api_phase4.json")
    violations: list[str] = []

    for module_name in _ALL_ENGINE_MODULE_NAMES:
        baseline_names = baseline.get(module_name)
        if baseline_names is None:
            violations.append(f"{module_name} (no baseline recorded)")
            continue

        current_names = _get_module_public_api(module_name)
        baseline_set = set(baseline_names)
        current_set = set(current_names)

        missing = baseline_set - current_set
        if missing:
            violations.append(f"{module_name}: missing names {sorted(missing)}")

    assert violations == [], "Public API changed in engine modules:\n" + "\n".join(
        f"  - {v}" for v in violations
    )


# ============================================================================
# IMPORT GRAPH TESTS
# ============================================================================


def test_action_and_app_use_same_engine() -> None:
    """Verify the App and Action code paths use the same engine modules.

    Imports both ``scripts.run_action`` and ``lychee.queue`` and checks
    that each engine module resolves to the same object in
    ``sys.modules``.  Since Python caches modules, this is true by
    construction, but the test documents and locks the invariant.
    """
    # P5-R6
    # Ensure both code paths are imported.
    importlib.import_module("scripts.run_action")
    importlib.import_module("lychee.queue")

    for module_name in _ALL_ENGINE_MODULE_NAMES:
        assert module_name in sys.modules, (
            f"Engine module {module_name} not found in sys.modules after "
            f"importing both scripts.run_action and lychee.queue"
        )
        # Verify it's a real module object, not a mock or wrapper.
        mod = sys.modules[module_name]
        assert hasattr(mod, "__file__"), (
            f"Engine module {module_name} in sys.modules does not have "
            f"__file__ attribute — may be a namespace package or mock"
        )


# ============================================================================
# ACCEPTANCE TESTS
# ============================================================================


def test_accept_engine_package_diff_empty() -> None:
    """Acceptance: engine package diff is empty between App and Action paths.

    Wraps ``test_engine_modules_not_modified`` to serve as the explicit
    acceptance test for the engine-unchanged requirement.
    """
    # P5-R6
    test_engine_modules_not_modified()


def test_accept_engine_code_untouched() -> None:
    """Acceptance: review.py has zero modifications (diff-verified).

    Combines file-existence and hash verification to confirm the
    engine's core review module is untouched.
    """
    # P5-R6
    review_path = _SRC_DIR / "review.py"
    assert review_path.exists(), f"review.py not found at {review_path}"

    content = review_path.read_bytes().replace(b"\r\n", b"\n")
    actual_hash = hashlib.sha256(content).hexdigest()
    assert (
        actual_hash == _EXPECTED_REVIEW_SHA256
    ), "review.py has been modified (acceptance check failed)."


# ============================================================================
# SMOKE TESTS
# ============================================================================


def test_engine_unchanged_module_imports() -> None:
    """Smoke: ``import tests.test_engine_unchanged`` succeeds.

    Verifies this test module itself can be imported without errors,
    confirming all dependencies are available.
    """
    # P5-R6
    mod = importlib.import_module("tests.test_engine_unchanged")
    assert mod is not None


# ============================================================================
# SANITY TESTS
# ============================================================================


def test_engine_unchanged_still_passes() -> None:
    """Sanity: the public API baseline is current.

    Wraps ``test_engine_public_api_unchanged`` as a sanity check that
    the API baseline fixture is up-to-date with the current codebase.
    """
    # P5-R6
    test_engine_public_api_unchanged()


# ============================================================================
# REGRESSION TESTS
# ============================================================================


def test_engine_hash_baseline_covers_all_strict_modules() -> None:
    """Regression: baseline fixture has a hash for every strict engine module.

    Guards against accidentally removing an entry from the baseline
    fixture file.
    """
    # P5-R6
    baseline: dict[str, str] = _load_json_fixture("engine_hashes_phase4.json")
    for module_file in _STRICT_ENGINE_MODULES:
        assert module_file in baseline, (
            f"Missing baseline hash for {module_file} in " f"engine_hashes_phase4.json"
        )


def test_engine_api_baseline_covers_all_modules() -> None:
    """Regression: API baseline fixture has an entry for every engine module.

    Guards against accidentally removing an entry from the baseline
    fixture file.
    """
    # P5-R6
    baseline: dict[str, list[str]] = _load_json_fixture("engine_api_phase4.json")
    for module_name in _ALL_ENGINE_MODULE_NAMES:
        assert module_name in baseline, (
            f"Missing baseline API for {module_name} in " f"engine_api_phase4.json"
        )
