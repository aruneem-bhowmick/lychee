# Development

Local setup, testing, code quality tools, and contribution workflow for
Lychee.

## Local setup

```bash
git clone https://github.com/aspect-analytics/lychee.git
cd lychee
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

The `[dev]` extra installs testing, linting, and type checking
dependencies: pytest, ruff, black, mypy, pre-commit, and related
plugins.

Install pre-commit hooks:

```bash
pre-commit install
```

## Code quality tools

### Ruff

Linter and formatter. Checks for errors (E), pyflakes (F), isort (I),
naming (N), warnings (W), pyupgrade (UP), bugbear (B), simplify (SIM),
and ruff-specific rules (RUF).

```bash
ruff check src/ tests/ scripts/
ruff format src/ tests/ scripts/
```

### Black

Code formatter. 100-character line length.

```bash
black --check src/ tests/ scripts/
```

### Mypy

Static type checker in strict mode. Python 3.11 target.
`ignore_missing_imports` is `false` — all imports must have type stubs.

```bash
mypy
```

### Pre-commit hooks

The `.pre-commit-config.yaml` runs on every commit:

- **ruff** — lint with `--fix --exit-non-zero-on-fix`, then format
- **black** — formatting check
- **pre-commit-hooks** — trailing whitespace, end-of-file fixer,
  YAML/TOML validation, large file detection
- **mypy** — type checking with `pydantic` and `types-PyYAML` stubs

## Running tests

```bash
pytest
```

This runs all tests except those marked `e2e` (excluded by default in
`pyproject.toml`). Coverage is measured automatically with a minimum
threshold of 80%. Branch coverage is enabled.

The default pytest invocation is equivalent to:

```bash
pytest -m 'not e2e' --cov=src/lychee --cov-report=term-missing --cov-fail-under=80
```

### Test markers

| Marker | Description |
|--------|-------------|
| `e2e` | End-to-end tests requiring live GitHub and Claude API access |

### Running specific tests

```bash
# Single test file
pytest tests/test_review.py

# Single test function
pytest tests/test_review.py::test_run_review_map_reduce

# Tests matching a keyword
pytest -k "triage"
```

## Test organization

Tests live in the `tests/` directory with one test file per source
module:

| Test file | Source module | Coverage area |
|-----------|-------------|---------------|
| `test_config.py` | `config.py` | Schema validation, unknown key rejection |
| `test_models.py` | `models.py` | Pydantic model validation, enum behavior |
| `test_review.py` | `review.py` | Review orchestration, model selection, map-reduce |
| `test_claude.py` | `claude.py` | API calls, tool extraction, usage tracking |
| `test_prompt.py` | `prompt.py` | System/user message construction |
| `test_render.py` | `render.py` | Comment rendering, severity ordering |
| `test_github_client.py` | `github_client.py` | API wrapper, file fetching |
| `test_context.py` | `context.py` | PR context assembly |
| `test_poster.py` | `poster.py` | Comment upsert, deduplication |
| `test_commands.py` | `commands.py` | Command parsing |
| `test_command_render.py` | `command_render.py` | Command response formatting |
| `test_command_dispatch.py` | — | Command routing and authorization integration |
| `test_authorization.py` | `authorization.py` | Permission checking |
| `test_triage.py` | `triage.py` | Classification, cheap review path |
| `test_webhook.py` | `webhook.py` | Signature verification, event filtering |
| `test_queue.py` | `queue.py` | Async queue, backpressure, worker pool |
| `test_state_store.py` | `state_store.py` | SQLite CRUD, upsert transactions |
| `test_health.py` | `health.py` | Health checks, metrics collection |
| `test_app_auth.py` | `app_auth.py` | JWT generation, token lifecycle |
| `test_cost.py` | `cost.py` | Pricing computation, budget enforcement |
| `test_rate_limiter.py` | `rate_limiter.py` | Token bucket, retry logic |
| `test_dedup.py` | `dedup.py` | Fingerprinting, cross-push dedup |
| `test_diff_mapping.py` | `diff_mapping.py` | Position mapping for inline comments |
| `test_inline_render.py` | `inline_render.py` | Finding formatting |
| `test_observability.py` | `observability.py` | Correlation IDs, structured logging |
| `test_action.py` | `run_action.py` | Action entrypoint integration |
| `test_app_integration.py` | — | Multi-repo, cross-repo, engine tracing |
| `test_engine_unchanged.py` | — | Engine hash verification, API baseline |
| `test_e2e.py` | — | Full pipeline with live APIs |

### Fixture system

Test fixtures live in `tests/fixtures/`. These include PR event payloads,
review result snapshots, and engine integrity hashes. Tests reference
fixtures via `conftest.py` helpers.

Golden snapshot tests use `pytest-snapshot` to compare rendered output
against saved baselines. To update snapshots after an intentional change:

```bash
pytest --snapshot-update
```

## E2E testing

End-to-end tests (`test_e2e.py`) run the full review pipeline against
live GitHub and Claude APIs using a throwaway canary repository. They are
excluded from default CI runs via the `-m 'not e2e'` filter.

See [CANARY-SETUP.md](CANARY-SETUP.md) for canary repository setup
instructions.

## CI pipeline

The CI workflow (`.github/workflows/ci.yml`) runs on pushes to `main`
and on pull requests. It has four jobs:

| Job | What it checks |
|-----|----------------|
| `lint` | ruff check + black format check |
| `type-check` | mypy strict mode |
| `engine-unchanged` | Engine integrity hash verification |
| `test` | pytest with 80% coverage minimum |

Coverage reports are uploaded to Codecov on pushes to `main`.

## Dry-run mode

For local development, use dry-run mode to test the review pipeline
without making API calls:

```bash
lychee review --dry-run --fixture tests/fixtures/pr_payload.json
```

This loads the fixture file, builds prompts, runs the rendering
pipeline, and prints the output to stdout.

## Project structure

```
src/lychee/
  __main__.py          CLI entry point
  config.py            Configuration loading and validation
  models.py            Domain models (ReviewResult, Finding, enums)
  review.py            Review orchestration, map-reduce
  claude.py            Anthropic API client
  prompt.py            Prompt construction
  github_client.py     GitHub API wrapper
  context.py           PR context assembly
  triage.py            PR classification
  render.py            Review comment rendering
  inline_render.py     Inline comment formatting
  command_render.py    Command response rendering
  poster.py            Comment posting (upsert)
  commands.py          Command parsing
  authorization.py     User authorization
  diff_mapping.py      Diff position mapping
  dedup.py             Finding deduplication
  cost.py              Cost computation and budgets
  rate_limiter.py      Rate limiting and retry
  observability.py     Logging and correlation
  webhook.py           Webhook handler
  app_auth.py          GitHub App authentication
  queue.py             Job queue and worker pool
  state_store.py       SQLite state persistence
  health.py            Health checks and metrics

scripts/
  run_action.py        GitHub Actions entry point
  run_server.py        Server entry point

tests/
  conftest.py          Shared fixtures and mocks
  fixtures/            PR payloads, snapshots, hashes
  test_*.py            One test file per module
```

## Code conventions

- **Line length:** 100 characters (enforced by ruff and black).
- **Immutable models:** All Pydantic models and dataclasses are frozen.
- **Pure functions:** Prompt construction and rendering are pure functions
  with no side effects.
- **Typed exceptions:** Each module defines its own exception types
  (`AppAuthError`, `BudgetExceededError`, `PosterError`, etc.).
- **No global state:** Clients and infrastructure are constructed at the
  entry point and passed down.
- **ContextVars:** Correlation IDs use `contextvars.ContextVar` for
  per-request scoping without threading through function signatures.
