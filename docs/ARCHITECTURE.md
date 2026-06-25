# Architecture

Lychee is an automated PR review tool powered by Claude. It reads pull
request diffs and metadata from GitHub, sends them to the Anthropic API for
structured analysis, and posts the results back as PR comments. It operates
in two deployment modes with a shared review engine.

## Deployment modes

### CLI mode (GitHub Actions)

```
PR event  -->  run_action.py  -->  GitHub API  -->  review engine  -->  poster  -->  PR comment
                                                       |
                                                   Claude API
```

The GitHub Actions runner triggers `scripts/run_action.py` on PR events.
The script reads the event payload from `GITHUB_EVENT_PATH`, fetches PR
context from the GitHub API, runs the review engine, and posts the result.
No persistent state, no long-lived process.

Entry point: `scripts/run_action.py`

### Server mode (GitHub App)

```
GitHub  -->  webhook  -->  queue  -->  worker pool  -->  review engine  -->  poster  -->  PR comment
  |            |                          |                  |
  |       signature                  app_auth            Claude API
  |       verification            (JWT + tokens)
  |
  +--- /health, /metrics (monitoring)
```

The server receives signed webhook events from GitHub, verifies HMAC-SHA256
signatures, enqueues jobs, and processes them through an async worker pool.
Authentication uses GitHub App JWTs exchanged for short-lived installation
tokens. State persists in SQLite.

Entry point: `scripts/run_server.py`

## Review pipeline

Both modes share the same review pipeline:

1. **Context assembly** — Fetch the PR diff, changed file contents (up to
   100 KB each, 50 files max by default), commit messages, PR metadata,
   and optional conventions file. Output: a `ReviewContext` object.

2. **Triage** (optional) — If `features.triage_pass` is enabled, send the
   context to a cheap model (Haiku) to classify the PR as `trivial` or
   `substantive`. Trivial PRs get a lightweight review. Substantive PRs
   proceed to the full pipeline.

3. **Model selection** — Choose the Claude model based on context size.
   Small PRs use `model.default` (Sonnet). PRs exceeding 100,000
   characters use `model.large_pr` (Opus). Scope rules can override the
   model per path or label.

4. **Prompt construction** — Build a system prompt (persona, rubric,
   severity definitions, ripeness definitions, tone instructions,
   optional conventions) and a user message (PR metadata, commits, diff,
   file contents). The system prompt uses Anthropic's prompt caching
   via ephemeral cache control blocks.

5. **Claude API call** — Send the prompt to Claude with tool use. The
   model must call `submit_review` with a structured `ReviewResult`:
   ripeness verdict, summary, file walkthrough, and a list of typed
   findings.

6. **Rendering** — Convert the `ReviewResult` into a Markdown comment
   with sections: header with ripeness badge, Nectar (summary), The Peel
   (walkthrough), and Pits (findings filtered by severity threshold).

7. **Posting** — Post or update the comment on the PR. Existing comments
   are found by the `<!-- lychee:review -->` HTML marker and updated in
   place (upsert). Inline comments are posted as review comments on
   specific diff lines when `features.inline_comments` is enabled.

## Map-reduce for large PRs

When a PR has more changed files than `review.max_files` (default 50),
the engine switches to a map-reduce strategy:

1. **Partition** — Split changed files into groups of 10.
2. **Map** — Run a separate Claude review call for each group. Each call
   receives only the diff and file contents for its group.
3. **Reduce** — Send all partial results to Claude with instructions to
   merge them into a single coherent review.
4. **Merge** — Aggregate token usage across all calls. The final
   `ReviewResult` comes from the reduce phase.

Thresholds: `_MAP_REDUCE_FILE_THRESHOLD` = 50 files,
`_MAP_GROUP_SIZE` = 10 files per group,
`_LARGE_PR_THRESHOLD` = 100,000 characters.

Implementation: `src/lychee/review.py`

## Module map

### Domain layer

| Module | Purpose |
|--------|---------|
| `models.py` | `ReviewResult`, `Finding`, enums (`Severity`, `Ripeness`, `Category`) |
| `config.py` | `LycheeConfig` and nested Pydantic models, `.lychee.yml` loading |

### GitHub integration

| Module | Purpose |
|--------|---------|
| `github_client.py` | GitHub API wrapper: PR data, diffs, file contents, commit messages |
| `context.py` | Assembles `ReviewContext` from GitHub data and config |

### AI integration

| Module | Purpose |
|--------|---------|
| `claude.py` | `ClaudeClient`: Anthropic API calls with tool use, retry, usage extraction |
| `prompt.py` | System/user prompt construction, `submit_review` tool schema |

### Review engine

| Module | Purpose |
|--------|---------|
| `review.py` | Pipeline orchestration, model selection, map-reduce |
| `triage.py` | Lightweight PR classification (trivial vs. substantive) |

### Output

| Module | Purpose |
|--------|---------|
| `render.py` | Full review comment rendering (Nectar, Peel, Pits sections) |
| `inline_render.py` | Single inline comment formatting |
| `command_render.py` | Command-specific response rendering (peel, juice, pit, ripe) |
| `poster.py` | Comment posting with upsert logic, state markers |

### Features

| Module | Purpose |
|--------|---------|
| `commands.py` | `@lychee` command parsing |
| `authorization.py` | User allowlist checks for commands |
| `diff_mapping.py` | Maps file/line to GitHub diff position for inline comments |
| `dedup.py` | Finding fingerprinting (SHA-256) and cross-push deduplication |

### Cost and reliability

| Module | Purpose |
|--------|---------|
| `cost.py` | Token cost computation, budget enforcement, cost formatting |
| `rate_limiter.py` | Token bucket rate limiter, exponential backoff with jitter |

### Observability

| Module | Purpose |
|--------|---------|
| `observability.py` | Correlation IDs (ContextVar), structured JSON logging |

### Server infrastructure

| Module | Purpose |
|--------|---------|
| `webhook.py` | Webhook handler, HMAC-SHA256 verification, event filtering |
| `app_auth.py` | GitHub App JWT generation, installation token lifecycle |
| `queue.py` | Async job queue with backpressure, worker pool |
| `state_store.py` | SQLite state persistence for reviews and installations |
| `health.py` | Health checks and runtime metrics collection |

## Database schema

Server mode uses SQLite with two tables:

**`reviews`** — Tracks review state per PR.

| Column | Type | Description |
|--------|------|-------------|
| `repo_full_name` | TEXT | Repository (owner/repo), part of PK |
| `pr_number` | INTEGER | PR number, part of PK |
| `installation_id` | INTEGER | GitHub App installation |
| `last_reviewed_sha` | TEXT | Last commit SHA reviewed |
| `review_status` | TEXT | Current status (pending, etc.) |
| `comment_id` | INTEGER | GitHub comment ID for upsert |
| `created_at` | TEXT | ISO 8601 timestamp |
| `updated_at` | TEXT | ISO 8601 timestamp |

**`installations`** — Tracks GitHub App installations.

| Column | Type | Description |
|--------|------|-------------|
| `installation_id` | INTEGER | GitHub installation ID, PK |
| `account_login` | TEXT | GitHub account name |
| `repos_count` | INTEGER | Number of repos in installation |
| `last_event_at` | TEXT | ISO 8601 timestamp |
| `created_at` | TEXT | ISO 8601 timestamp |

Both tables use `INSERT ... ON CONFLICT DO UPDATE` for upserts.

Implementation: `src/lychee/state_store.py`

## Design decisions

**Immutable models.** All Pydantic models and dataclasses are frozen. No
in-place mutation after construction. This prevents accidental state
sharing between pipeline stages.

**Pure functions for prompt and render.** Prompt construction
(`src/lychee/prompt.py`) and comment rendering (`src/lychee/render.py`)
are pure functions that take data in and return strings. No side effects,
no network calls. This makes them deterministic and testable in isolation.

**ContextVars for correlation.** Each review gets a unique correlation ID
stored in a `ContextVar`. Log entries automatically include the
correlation ID without threading it through every function signature.

**Factory construction.** Clients and infrastructure are constructed at
the entry point (`run_action.py` or `run_server.py`) and passed down.
No singletons or global state.

**Error boundaries.** Each module defines its own typed exceptions
(`AppAuthError`, `BudgetExceededError`, `PosterError`,
`QueueFullError`, `RateLimitExhaustedError`). Callers catch specific
errors and handle them at the appropriate level.

**Comment upsert.** Reviews update existing comments instead of creating
new ones. The `<!-- lychee:review -->` HTML marker identifies the
comment to update. This avoids notification spam on re-review.

## Non-goals

Lychee does not:

- Gate merges or block CI pipelines
- Auto-approve or auto-merge pull requests
- Store source code, diffs, or file contents beyond the review lifecycle
- Replace linters, test runners, or static analysis tools
- Operate as a multi-tenant SaaS platform
