# Changelog

All notable changes to the lychee project are documented here.

## [0.1.5] — GitHub App

Lychee can now run as a centralized GitHub App, reviewing PRs across multiple
repositories under its own identity. The server receives webhook events,
authenticates per-installation, queues jobs for async processing, and persists
state in SQLite. A full deployment stack (Dockerfile, health checks, CI gate)
ships alongside the server code.

### Webhook Server (#35)

- Added `src/lychee/webhook.py`: async HTTP server built on Starlette that
  receives GitHub webhook POST requests, verifies HMAC-SHA256 signatures against
  a configured secret, and filters for events lychee acts on (`pull_request` and
  `issue_comment`)
- The server returns fast acknowledgments within GitHub's 10-second timeout and
  delegates event processing to an async callback
- Invalid signatures return HTTP 403; unrecognized events return 200 and are
  discarded; callback errors return 500 without crashing the server
- Added `scripts/run_server.py` entrypoint: reads required env vars
  (`LYCHEE_WEBHOOK_SECRET`, `LYCHEE_APP_ID`, `LYCHEE_PRIVATE_KEY_PATH`,
  `ANTHROPIC_API_KEY`), builds the ASGI app, and runs it under uvicorn
- Extended `src/lychee/config.py` with `AppConfig` (frozen Pydantic model):
  `webhook_secret`, `app_id`, `private_key_path` (required), plus
  `queue_workers`, `queue_max_size`, `state_backend`, `state_dsn`, `host`,
  `port` (optional with defaults). Unknown keys under `app.*` are rejected.
- Added `starlette`, `uvicorn`, and `pytest-asyncio` as dependencies
- 44 new tests in `tests/test_webhook.py` covering signature verification,
  event filtering, integration via `TestClient`, system tests, and parametrized
  regression snapshots
- 5 new tests in `tests/test_config.py` for `AppConfig`

### GitHub App JWT Auth (#36)

- Added `src/lychee/app_auth.py` with `AppAuthenticator`: loads a PEM private
  key at construction, generates 10-minute RS256-signed JWTs with a 60-second
  `iat` backdate for clock-skew tolerance, and exchanges them for short-lived
  installation access tokens via the GitHub API
- `InstallationToken` frozen dataclass holds the token, its Unix-timestamp
  expiry, and the installation ID; the `is_expired` property accounts for a
  5-minute refresh buffer
- Tokens are cached in-memory keyed by installation ID; subsequent calls for
  the same installation skip the HTTP mint when the cached token is still valid
- `AppAuthError` exception carries a message and an optional HTTP status code
- Added `from_installation_token()` classmethod on `GitHubClient` to create
  clients authenticated via `github.Auth.Token`
- Added `PyJWT` and `cryptography` as dependencies
- 28 tests in `tests/test_app_auth.py` (unit, regression, integration,
  acceptance, smoke); 2 new tests in `tests/test_github_client.py`

### Durable State Store (#37)

- Added `src/lychee/state_store.py` with `SqliteStateStore` backed by
  `aiosqlite`: stores per-PR state (`ReviewState`) and per-installation
  metadata (`InstallationState`)
- Composite primary key `(repo_full_name, pr_number)` for reviews;
  `installation_id` PK for installations
- `INSERT ... ON CONFLICT DO UPDATE` upserts that preserve `created_at`
  timestamps; timestamps stored as ISO 8601 UTC strings
- `list_reviews()` supports dynamic filtering by `repo_full_name`,
  `installation_id`, and `review_status`
- `StateStore` ABC defines the async CRUD interface; `create_state_store()`
  factory returns `SqliteStateStore` for `"sqlite"` and raises `ValueError`
  for anything else
- Idempotent `initialize()` and `close()` (safe to call multiple times)
- Added `aiosqlite` as a dependency
- 33 tests covering unit, integration (`:memory:` DSN), system
  (file-backed persistence, concurrent upserts), acceptance, smoke, sanity,
  and regression categories

### Async Job Queue and Worker Pool (#38)

- Added `src/lychee/queue.py`: `ReviewQueue` wraps `asyncio.Queue` with a
  configurable max size; `enqueue()` raises `QueueFullError` immediately when
  full instead of blocking the webhook handler
- `WorkerPool` spawns N async worker tasks (configurable via
  `AppConfig.queue_workers`, default 4); each worker loops: dequeue a job,
  obtain an installation token, construct an authenticated `GitHubClient`,
  run the review engine or command dispatcher, post results, and update the
  state store with status transitions
- Workers catch all exceptions so a single failure does not take down the pool
- `event_to_job()` extracts installation ID, repo name, and PR number from
  webhook payloads and returns a `Job` ready for enqueuing
- Updated `webhook.py` to return HTTP 503 (`{"status": "queue_full"}`) on
  `QueueFullError` so GitHub backs off and retries
- Rewrote `scripts/run_server.py` to construct the full stack: queue, auth,
  state store, worker pool, and webhook server with Starlette lifecycle hooks
- 48 tests in `tests/test_queue.py`; 1 new test in `tests/test_webhook.py`

### Health Checks, Dockerfile, and Deployment Workflow (#39)

- Added `src/lychee/health.py` with `HealthChecker` and `MetricsCollector`:
  - `HealthChecker` checks state store connectivity and worker pool liveness;
    returns a `HealthStatus` dataclass with `healthy`, `server_up`,
    `state_store_connected`, `workers_alive`, and `details`
  - `MetricsCollector` tracks uptime, queue depth, queue capacity,
    active/total workers, and cumulative job processed/failed counters
- Two new HTTP routes: `GET /health` (200 if healthy, 503 if not) and
  `GET /metrics` (JSON snapshot of all runtime metrics)
- Graceful shutdown via a module-level `_draining` flag set when the lifespan
  context exits; workers are drained with a 30-second timeout before the state
  store is closed
- Added `Dockerfile` based on `python:3.11-slim` with a `HEALTHCHECK`
  directive probing `/health` every 30 seconds; no secrets baked into the image
- Added `.github/workflows/deploy.yml`: template deployment workflow triggered
  by manual dispatch or semantic version tag pushes; builds the Docker image
  with Buildx caching and pushes to `ghcr.io`
- 37 tests in `tests/test_health.py`

### Engine Integrity Verification (#40)

- Added `tests/fixtures/engine_hashes_phase4.json` and
  `tests/fixtures/engine_api_phase4.json`: SHA-256 hashes for 16 strict engine
  module source files and public API baselines for all 18 engine modules
- Rewrote `tests/test_engine_unchanged.py` (13 tests): hash-based verification,
  public API surface checks (additive extensions allowed, removals caught),
  import graph validation confirming both `run_action` and `lychee.queue`
  resolve to the same engine module objects, module list completeness check,
  baseline fixture validation
- Added `tests/test_app_integration.py` (8 tests): multi-repo review,
  cross-repo commands, dedup across pushes, engine call tracing, import
  identity sanity checks
- New `engine-unchanged` CI job in `.github/workflows/ci.yml` runs the
  engine integrity tests as a standalone gate

---

## [0.1.4] — Command Interface

Users can now interact with lychee by commenting `@lychee` commands on pull
requests. Four commands are supported: `peel` (full review), `juice` (summary
only), `pit` (highest-severity finding), and `ripe?` (merge-readiness verdict).
Commands are authorized against a configurable allowed-users list. Repository
owners can also scope review behavior by file path and PR label.

### Command Parser (#30)

- Added `src/lychee/commands.py` with `parse_command()`: extracts the first
  `@lychee` command from a GitHub issue comment body and returns a typed
  `ParsedCommand`, `UnknownCommand`, or `None`
- `Command` StrEnum with four members: `peel`, `juice`, `pit`, `ripe?`
- Case-insensitive mention detection with negative lookaround to prevent false
  matches on `@lychee-bot` or similar
- Trailing punctuation is stripped from the command token, but `?` is preserved
  for `ripe?`
- Multiple mentions in one comment: first one wins
- `HELP_TEXT` constant listing all commands with one-line descriptions
- 47 tests in `tests/test_commands.py` (100% coverage on `commands.py`)

### Scoped Behavior Overrides (#31)

- Added `ScopeRule` (frozen Pydantic model) to `config.py`: per-path or
  per-label overrides specifying glob patterns, label names, and optional
  overrides for `model`, `severity_threshold`, `tone`, or an `ignore` flag
  to skip matched files
- Added `AuthorizationConfig` with an `allowed_users` list; empty list means
  open access
- `should_ignore_file()` checks whether a file should be excluded from review
  context by matching against scope rules with `ignore=True`; first-match-wins
  semantics
- `resolve_scope_overrides()` returns effective config overrides from the first
  matching scope rule
- `build_context()` gains an optional `pr_labels` parameter; files matching
  `ignore=True` rules are filtered out before context assembly
- 40+ tests in `tests/test_scoped_behavior.py`; 6 new tests in
  `tests/test_config.py`; 4 new tests in `tests/test_context.py`

### Tone Tuning (#32)

- Strengthened the `concise` and `detailed` tone instruction strings in
  `prompt.py` so each produces reliably distinct system prompts:
  - **Concise**: bullet-list walkthroughs, one-sentence findings, skip
    walkthrough for straightforward PRs
  - **Detailed**: multi-paragraph walkthroughs, findings with rationale and
    examples, suggestion blocks with ready-to-apply code
- Balanced tone remains unchanged (empty string; default persona applies)
- Updated golden snapshot fixtures for concise and detailed
- 21 new tests in `tests/test_tone.py`

### Command Dispatch and Authorization (#34)

- Added `src/lychee/authorization.py` with `is_authorized()` and
  `format_refusal()`: checks the commenter against the allowed-users list
  (case-insensitive); refusal messages name the user but do not reveal the
  allowed list
- Added `src/lychee/command_render.py` with four render functions:
  - `render_peel_response`: full review (delegates to `render_comment`)
  - `render_juice_response`: Nectar/summary section only
  - `render_pit_response`: single highest-severity finding
  - `render_ripe_response`: ripeness badge + one-line merge-readiness verdict
- Extended `scripts/run_action.py` to handle `issue_comment` events: parse,
  auth check, review, render, post via `create_issue_comment`
- Auth runs after parsing but before the engine, so unauthorized users never
  trigger API calls
- `features.commands` gates command processing; when disabled, command events
  exit immediately with no API calls
- Updated `.github/workflows/review.yml` with `issue_comment: types: [created]`
  trigger
- 31 tests in `test_command_render.py`; 38 tests in `test_command_dispatch.py`;
  3 tests in `test_action.py`; full `test_authorization.py` suite

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
