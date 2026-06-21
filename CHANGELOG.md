# Changelog

All notable changes to the lychee project are documented here.

## [0.1.0] — Initial Package Scaffold

Initial repository layout: installable `lychee` package with all module stubs,
Click CLI entry point, sample configuration file, and test infrastructure.

### Package Skeleton (#1)

- `pyproject.toml` using hatchling with runtime dependencies: `anthropic`,
  `PyGithub`, `PyYAML`, `pydantic`, `click`, `httpx`
- `src/lychee/__init__.py` with `__version__ = "0.1.0"`
- `lychee` entry point registered under `project.scripts`
- Nine module stubs under `src/lychee/` with complete type-annotated signatures
  (`models`, `config`, `github_client`, `context`, `prompt`, `claude`, `render`,
  `review`, `poster`)
- Click CLI group with `review` subcommand (`--dry-run`, `--fixture`)
- `.github/workflows/review.yml` stub with `pull_request` trigger and
  least-privilege permissions
- `.lychee.yml` sample config with all documented keys at defaults
- 22 tests in `tests/test_scaffold.py`

### Domain Contracts (#2)

- `Severity`, `Ripeness`, and `Category` as `StrEnum` members
- `Finding` and `ReviewResult` as frozen Pydantic v2 models with
  `extra="forbid"` (unknown keys raise `ValidationError` at the boundary)
- Field validators rejecting empty strings on required fields
- `ReviewResult.from_tool_input()` for deserializing Claude tool-call output
- `ReviewResult.to_tool_schema()` returns the `submit_review` JSON Schema
  for the Anthropic API `tools` parameter
- 28 tests in `tests/test_models.py` with a golden snapshot for the tool schema

### Configuration Loader (#3)

- Four frozen Pydantic v2 models: `ModelConfig`, `ReviewConfig`,
  `FeaturesConfig`, `LycheeConfig`
- `extra="forbid"` on every nested model; unknown keys at any depth raise
  `LycheeConfigError` naming the offending key
- `load_config()`: reads `.lychee.yml`, validates, fills defaults for omitted
  keys; absent file returns defaults; malformed YAML wraps as
  `LycheeConfigError`
- 34 tests in `tests/test_config.py` (100% coverage on `config.py`)

### Comment Renderer (#4)

- `render_comment()` converts a `ReviewResult` into the Markdown comment
  posted on PRs: hidden marker, header with model name and Ripeness badge,
  Nectar summary, walkthrough (The Peel), findings grouped by severity (Pits),
  and footer
- Severity groups render in `critical > major > minor > info` order; empty
  groups are skipped
- Suggestion fence blocks nest under list items with two-space indentation
- Optional `cost_line` parameter
- Four golden snapshot files (`golden_ripe.md`, `golden_unripe.md`,
  `golden_sour.md`, `golden_no_findings.md`)
- 32 tests in `tests/test_render.py` (100% coverage)

### Dry-Run Mode (#5)

- `run_review_dry()` runs the review pipeline from fixture files with no
  network calls: reads a PR fixture JSON, loads a bundled `ReviewResult`,
  validates through the domain schema, and returns the rendered comment
- CLI: `lychee review --dry-run --fixture <path>` prints the formatted
  comment to stdout
- 21 tests in `tests/test_dry_run.py` plus 1 gated e2e test

### Dev Toolchain and CI (#7)

- `.pre-commit-config.yaml`: ruff, black, mypy, pre-commit-hooks (all pinned)
- `.github/workflows/ci.yml`: three parallel jobs (lint, type-check, test)
  on `ubuntu-latest`, Python 3.11; Codecov upload on pushes to `main`
- Line width standardized to 100 characters for ruff, black, and all source
- Coverage gate at 80% via `--cov-fail-under=80` in pytest addopts
- 13 tests in `tests/test_ci_tooling.py`

### Test Fixtures and Harness (#8)

- Shared fixture data: `pr_large.json` (55-file PR), `diff_simple.txt`,
  `diff_large.txt`, `review_result_unripe.json`, `review_result_sour.json`
- Enriched `pr_simple.json` with `files` array, `state`, and `base.sha`
- `conftest.py` populated with 10 pytest fixtures: 4 `ReviewResult` variants,
  4 data fixtures, 2 client mocks
- 25 tests in `tests/test_fixtures.py`
