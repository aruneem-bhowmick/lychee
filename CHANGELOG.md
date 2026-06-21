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

## [0.1.3] — Inline Commenting

Findings can now be posted as inline review comments pinned to specific diff
lines, in addition to the summary comment. When a finding maps to a line in
the diff, it goes inline; when it does not (file-level findings, lines outside
the changed hunks), it falls back to a visible section in the summary. One
`create_review` API call per review, not N individual comments.

### Inline Review Comment Posting (#24)

- Added `src/lychee/diff_mapping.py`: parses unified diffs and builds a
  `{file: {line: position}}` map for GitHub's pull request review API, which
  requires a 1-based position offset within the diff rather than a line number
- Added `src/lychee/inline_render.py`: formats a `Finding` as a GitHub review
  comment body with severity emoji, severity label, category tag, and message;
  appends a ` ```suggestion ` block when the finding carries a suggestion
- Extended `src/lychee/render.py` with an optional `fallback_findings`
  parameter on `render_comment()`; non-empty fallback renders a collapsible
  `<details>` block after the Pits section
- Added `InlineReviewPoster` to `src/lychee/poster.py`: splits findings into
  inline-eligible and fallback buckets, renders each inline finding, and
  submits them through `pr.create_review(event="COMMENT", comments=[...])`
- 76 new tests across 4 files

### Diff Position Mapping Fix (#25)

- Fixed an off-by-one error in position counting: the first `@@` hunk header
  was previously counted as position 1, shifting every subsequent line by one
- `build_position_map()` now returns `dict[str, dict[int, DiffPosition]]`
  (frozen dataclass with `head_line` and `position`) instead of bare integers
- `map_finding_to_position()` now takes `(file, line, position_map)` instead
  of `(finding, position_map)`, decoupling the mapping layer from the `Finding`
  model
- Path extraction uses `+++ b/...` headers instead of `diff --git` lines,
  correctly handling deleted files, added files, and renames
- Binary file markers and `\ No newline at end of file` markers are now
  skipped instead of incrementing the position counter
- 38 tests in `tests/test_diff_mapping.py` with three new `.patch` fixture
  files

### Cross-Push Deduplication (#26)

- Added `src/lychee/dedup.py`: fingerprint-based identity tracking so that
  only new or changed findings produce inline comments on re-push
- Each posted finding is reduced to a fingerprint (file path, line number,
  severity, 12-char SHA-256 prefix of the message text) and stored in the
  summary comment's state marker
- On the next review cycle, the poster extracts previous fingerprints and
  filters out any finding whose fingerprint already exists in state
- If state is absent or malformed, dedup is skipped and all findings are
  posted fresh
- 34 tests in `tests/test_dedup.py`; 4 new tests in `tests/test_poster.py`

### Suggestion Block Formatting (#27)

- Revised inline comment format to `{emoji} **[{Severity}]** (*{category}*):
  {message}` for better visual distinction between severity and category
- Added whitespace normalization to `render_suggestion_block()`: strips
  trailing whitespace from each line and removes leading/trailing blank lines
  inside the fence, preventing unwanted empty lines in GitHub's rendered
  suggestion diff
- 18 new tests in `tests/test_inline_render.py` (total: 38, 100% coverage)

### Unmappable Fallback Rendering (#28)

- Moved the fallback section from after Pits to between Nectar and The Peel
  so authors see unmappable findings before the code walkthrough
- Replaced the `<details>` block (hidden behind a click) with a
  `### Findings not on changed lines` heading, making findings always visible
- Each fallback finding uses a dedicated format with severity leading,
  colon-notation location, italic category, and a text label explaining why
  the finding appears in the summary
- Suggestions in fallback findings render in plain fenced code blocks, not
  ` ```suggestion ` blocks (GitHub's one-click-apply only works on inline
  review comments)
- `severity_threshold` now filters fallback findings; if all are below the
  threshold, the section is omitted
- 14 new tests in `tests/test_render.py` (total: 69)

### Feature Flag Wiring (#29)

- Connected the `features.inline_comments` config flag to the posting logic
  in `run_action.py`
- When the flag is on, the action fetches the PR diff, posts inline review
  comments via `InlineReviewPoster`, and folds unmappable findings into a
  fallback section in the summary; cross-push deduplication uses the state
  marker from the previous summary comment
- When the flag is off (default), behavior is unchanged
- Inline failures (`PosterError`) are caught and logged; the summary comment
  still posts
- Added `tests/test_engine_unchanged.py` with three regression tests
  confirming `src/lychee/review.py` was not modified (SHA-256 hash comparison
  and `git diff` check)
- 20 new tests in `tests/test_action.py`

---

## [0.1.2] — Robustness, Scale & Cost

Reviews are now cheaper, resilient to transient failures, and can handle large
PRs and concurrent workloads. Cost tracking, budget caps, rate limiting,
optional triage, and structured logging all ship in this version.

### Prompt Caching (#17)

- Added `build_system_prompt_blocks()` to `prompt.py`: wraps the system prompt
  in a content block with `cache_control: {"type": "ephemeral"}` for the
  Anthropic Messages API, reducing input token costs by about 90% on cache hits
- `ClaudeClient.review()` now accepts a plain string or a list of content
  blocks as its `system` parameter
- `run_review()` uses the block variant by default
- `build_system_prompt()` is unchanged and still available for callers that
  need a plain string
- 24 new tests across `test_prompt.py`, `test_claude.py`, and `test_review.py`

### Config-Driven Behavior (#18)

- Wired `tone`, `language`, `severity_threshold`, and model tiering through
  the review pipeline:
  - `build_system_prompt()` appends `## Tone` and `## Language` sections when
    values differ from defaults
  - `render_comment()` takes a `severity_threshold` parameter and filters
    findings below the threshold from the Pits section
  - `select_model()` in `review.py` returns `config.model.large_pr` when
    context exceeds 100k characters, `config.model.default` otherwise
  - `ClaudeClient.review()` takes a `model_override` parameter for per-call
    model selection
- All new parameters default to prior behavior; existing golden snapshots pass
  unchanged
- 30 new tests across 5 test files

### Map-Reduce for Large PRs (#19)

- When a PR exceeds `config.review.max_files` (default 50), files are
  partitioned into groups of 10, each reviewed individually (map phase), then
  partial results are merged into one `ReviewResult` (reduce phase)
- Small PRs still take the single-pass path, unchanged
- Sequential map calls (no parallelism): a 62-file PR produces 7 map groups +
  1 reduce call
- Partial failure tolerance: if some map groups fail, the pipeline continues
  with successful partials; if all groups fail, `ClaudeReviewError` is raised
- Usage aggregation sums all token fields across map partials and the reduce
  result
- Added `build_map_user_message()` and `build_reduce_user_message()` to
  `prompt.py`
- 38 new tests across `test_review.py` and `test_prompt.py`; new 62-file PR
  fixture

### Rate Limiting and Retries (#20)

- Added `src/lychee/rate_limiter.py` with a thread-safe token-bucket rate
  limiter and an exponential-backoff retry wrapper
- Pre-configured tiers: tier1 (5 capacity, 1/s refill) through tier4
  (50 capacity, 10/s refill)
- Retry logic respects `Retry-After` headers from `anthropic.RateLimitError`;
  optional jitter prevents thundering herd
- Retryable errors: 429, 500/529, connection errors. Non-retryable: 401, 400
  (propagate immediately)
- Two new optional parameters on `ClaudeClient.__init__`: `rate_limiter` and
  `retry_config`; both default to `None` so existing call sites are unchanged
- 31 new tests across `test_rate_limiter.py` and `test_claude.py`

### Cost Accounting and Budget Cap (#21)

- Added `src/lychee/cost.py` with `compute_cost()`, `compute_total_cost()`,
  `format_cost_line()`, and `check_budget()`
- `MODEL_PRICING` dict maps model IDs to per-million-token rates (input,
  output, cached-input); unknown models fall back to Sonnet pricing with a
  logged warning
- `budget_cap_usd` config field (optional, must be > 0 when set): the review
  engine checks cumulative spend after each Claude API call; if exceeded,
  `BudgetExceededError` is raised and the action posts an abort comment to the
  PR
- In map-reduce mode, budget checks run after each map group and after the
  reduce call
- Cost footer in PR comments shows dollar amount, input/output token counts,
  and cached-token count when present; controlled by
  `features.cost_footer` (default `true`)
- 45 new tests across 4 test files

### Optional Haiku Triage Pre-Pass (#22)

- Added `src/lychee/triage.py`: when `features.triage_pass` is enabled, a
  Haiku call classifies incoming PRs as **trivial** (typo fixes, dependency
  bumps, config-only changes, formatting) or **substantive** (new features,
  bug fixes, refactoring, security changes)
- Trivial PRs get a complete review from Haiku alone, skipping the more
  expensive Sonnet/Opus pipeline; substantive PRs proceed through normal model
  tiering
- Fail-safe: any triage error defaults to `substantive`, so a broken triage
  pass never silently downgrades review quality
- The triage prompt sends only file names, truncated body/diff, and a short
  classification instruction (no full rubric or persona)
- 29 tests in `tests/test_triage.py`

### Structured Observability (#23)

- Added `src/lychee/observability.py`: `ContextVar`-based correlation IDs tag
  every log record without passing IDs through function signatures
- `setup_structured_logging()` replaces root logger handlers with a JSON
  formatter (timestamp, logger name, level, correlation ID, message)
- `build_run_record()` / `emit_run_record()` produce a structured JSON record
  per review run: repo, PR number, head SHA, model, token usage, cost,
  ripeness, per-severity finding counts, duration, review strategy, triage
  verdict
- Run records never include PR content (title, body, diff); they identify the
  PR by repo + number + SHA only
- `run_review()` now measures wall-clock time with `time.monotonic()`
- `run_action.py` emits `review_complete` or `review_failed` run records with
  correlation IDs
- 30 new tests across `test_observability.py`, `test_action.py`, and
  `test_review.py`

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
