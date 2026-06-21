# Changelog

All notable changes to the lychee project are documented here.

## [0.1.1] — Review MVP

Lychee can now post real review comments on live pull requests. Opening or
pushing to a PR triggers an automated review via GitHub Actions. The engine
fetches PR context from GitHub, builds a structured prompt, sends it to
Claude, and upserts a formatted summary comment on the PR.

### GitHub Context Fetcher (#9)

- Added `src/lychee/github_client.py` with `GitHubClient`: wraps PyGithub
  and httpx to fetch PR data
  - `PullRequestRef`: frozen dataclass parsing `owner/repo#123` strings with
    format validation
  - `ChangedFile`: frozen dataclass for file diffs (filename, status,
    additions/deletions, patch text, decoded head content, rename tracking)
  - `get_pull_request()`, `get_diff()`, `get_changed_files()` (with
    `max_files`, `max_file_bytes`, and `ignore_globs` filtering),
    `get_file_content()`, `get_commit_messages()`, `get_conventions_file()`
- Added `src/lychee/context.py` with `ReviewContext` (frozen Pydantic model)
  and `build_context()`: assembles PR metadata, diff text, changed files,
  commit messages, and conventions into a single context object
- 60+ tests across `test_github_client.py` and `test_context.py`

### Prompt Builder (#10)

- Replaced the stub in `src/lychee/prompt.py` with four pure functions:
  - `build_system_prompt()`: assembles the static system prompt with the
    reviewer persona, review rubric (7 categories), severity definitions,
    ripeness definitions, output instructions, and optional project conventions
  - `build_user_message()`: formats PR context into a structured message with
    metadata, commit messages, unified diff, and changed file contents with
    language-tagged code blocks
  - `build_messages()`: wraps the user message in Messages API format
  - `get_tools()`: returns `[ReviewResult.to_tool_schema()]`
- All functions are pure: no I/O, no logging, no mutable state
- 34 tests in `tests/test_prompt.py` with golden snapshot fixtures

### Claude API Client (#11)

- Replaced the stubs in `src/lychee/claude.py` with `ClaudeClient`:
  - Forces Claude to respond via a `submit_review` tool call, then parses the
    structured output into a validated `ReviewResult`
  - Tracks token usage (input, output, cached) for downstream cost accounting
  - `ClaudeReviewError` wraps SDK connection errors, API status errors, missing
    tool-use blocks, unexpected tool names, and Pydantic validation failures
    into a single exception type
  - Conditional cache field extraction (only includes non-zero values)
- 24 tests in `tests/test_claude.py`

### Review Engine Orchestrator (#12)

- Replaced the `NotImplementedError` stub in `run_review()` with the working
  pipeline: parse the PR ref, fetch context from GitHub, build the prompt,
  send it to Claude, return the `ReviewResult`
- The orchestrator is ~20 lines with no branching; each component has its own
  tests and the orchestrator calls them in sequence
- Errors propagate to the caller without being caught (retry and rate-limiting
  decisions belong to the action layer)
- Log output records PR ref, model, ripeness, finding count, and usage dict;
  no PR content or diffs in the logs
- 19 tests in `tests/test_review.py`

### Summary Comment Poster (#13)

- Replaced the `SummaryPoster` stub in `poster.py` with upsert logic:
  - Scans existing PR comments for the `<!-- lychee:review -->` marker
  - Edits the existing marker comment in place on re-push (no duplicates)
  - Creates a new comment on first run or when a prior comment was deleted
  - Appends a `<!-- lychee:state {...} -->` marker for per-PR state tracking
    (last-reviewed SHA)
  - `extract_state()` reads the state dict back from a comment body
  - Wraps `GithubException` in `PosterError`
- 32 tests in `tests/test_poster.py` (100% branch coverage)

### GitHub Actions Entrypoint and Live CLI (#14)

- Added `scripts/run_action.py`: reads `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`,
  `GITHUB_EVENT_PATH`, and `GITHUB_REPOSITORY` from the environment; validates
  the event action (`opened`, `synchronize`, `reopened`); constructs clients,
  runs the engine, renders and posts the comment
- Extended the CLI with `--pr owner/repo#123` for live reviews and
  `--post/--no-post` to control whether the comment is posted or printed
- Replaced the placeholder in `.github/workflows/review.yml` with the working
  action; fork PRs are skipped via the `head.repo.full_name` guard so they
  cannot access secrets
- 35 new tests across `test_action.py` and `test_cli_live.py`

### End-to-End Canary Tests (#15)

- Added `.github/workflows/e2e.yml`: manually triggered workflow that runs the
  full review pipeline against a live canary repository with real GitHub and
  Claude API calls
- 5 gated e2e tests (`@pytest.mark.e2e`, excluded from default runs):
  module import smoke, config sanity, full review posting with section
  verification, idempotent repost, and run record emission with secret-leak
  check
- Added `docs-lychee/canary-setup.md` with setup instructions
- Added `pytest-timeout` dev dependency

### Documentation Reorganization (#16)

- Moved `docs-lychee/canary-setup.md` to `docs/CANARY-SETUP.md` so the
  operational guide is version-controlled and visible to collaborators
- `docs-lychee/` is now fully untracked (the `.gitignore` entry takes effect
  with no tracked files remaining)

---

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
