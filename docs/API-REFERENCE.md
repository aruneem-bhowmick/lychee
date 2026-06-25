# API Reference

HTTP endpoints exposed by the Lychee server, external API integrations,
and the CLI interface.

## Server endpoints

The server (GitHub App mode) exposes four HTTP routes. All routes are
defined in `scripts/run_server.py`.

### `POST /webhook`

Receives GitHub webhook events.

**Request headers:**

| Header | Required | Description |
|--------|----------|-------------|
| `X-Hub-Signature-256` | Yes | HMAC-SHA256 signature of the request body |
| `X-GitHub-Event` | Yes | Event type (e.g. `pull_request`, `issue_comment`) |
| `X-GitHub-Delivery` | Yes | Unique delivery ID |

**Request body:** JSON payload from GitHub (event-specific schema).

**Response codes:**

| Code | Condition |
|------|-----------|
| `200` | Event received but not applicable (silently ignored) |
| `202` | Event accepted and enqueued for processing |
| `403` | Missing, malformed, or invalid webhook signature |
| `500` | Internal server error during event processing |
| `503` | Job queue is full; GitHub should retry with backoff |

**Applicable events:**

| Event | Action | Behavior |
|-------|--------|----------|
| `pull_request` | `opened` | Enqueue a new review |
| `pull_request` | `synchronize` | Enqueue a re-review (updates existing comment) |
| `pull_request` | `reopened` | Enqueue a new review |
| `issue_comment` | `created` | Enqueue command processing if body contains `@lychee` |

Non-applicable events return `200` without processing.

Implementation: `src/lychee/webhook.py`

### `GET /`

Liveness probe. Returns `200` with a plain-text body confirming the
server is running.

### `GET /health`

Health check endpoint. Returns `200` when healthy, `503` when unhealthy.

**Response body (JSON):**

```json
{
  "healthy": true,
  "server_up": true,
  "state_store_connected": true,
  "workers_alive": true,
  "details": {}
}
```

| Field | Type | Description |
|-------|------|-------------|
| `healthy` | `bool` | Overall health status (all checks pass) |
| `server_up` | `bool` | Server process is running |
| `state_store_connected` | `bool` | SQLite state store is reachable |
| `workers_alive` | `bool` | At least one worker task is alive |
| `details` | `object` | Additional diagnostic information |

Implementation: `src/lychee/health.py`

### `GET /metrics`

Runtime metrics snapshot. Returns `200` with a JSON body.

**Response body (JSON):**

```json
{
  "uptime_seconds": 3600.5,
  "queue_size": 2,
  "queue_max_size": 100,
  "active_workers": 3,
  "total_workers": 4,
  "jobs_processed": 47,
  "jobs_failed": 1,
  "jobs_in_queue": 2
}
```

| Field | Type | Description |
|-------|------|-------------|
| `uptime_seconds` | `float` | Seconds since server start |
| `queue_size` | `int` | Current number of jobs in the queue |
| `queue_max_size` | `int` | Maximum queue capacity |
| `active_workers` | `int` | Number of workers currently processing a job |
| `total_workers` | `int` | Total worker tasks spawned |
| `jobs_processed` | `int` | Total jobs completed since start |
| `jobs_failed` | `int` | Total jobs that failed since start |
| `jobs_in_queue` | `int` | Alias for `queue_size` |

Implementation: `src/lychee/health.py`

## GitHub API usage

Lychee calls the following GitHub API endpoints. In CLI/Actions mode,
authentication uses `GITHUB_TOKEN`. In server mode, authentication uses
GitHub App installation tokens.

**Required permissions:**
- `contents: read` — File contents and repository data
- `pull-requests: write` — Post and update PR comments

**Endpoints called:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| Pull request data | GET | PR metadata (title, body, author, refs, labels) |
| Pull request diff | GET | Unified diff of changed files |
| Pull request files | GET | List of changed files with patch data |
| Repository contents | GET | File contents at the head ref (up to `max_file_bytes`) |
| Pull request commits | GET | Commit messages for context |
| Issue comments | GET/POST/PATCH | Read, create, and update review comments |
| Pull request reviews | POST | Create inline review comments (when `inline_comments` enabled) |

The GitHub client is implemented via PyGithub. See
`src/lychee/github_client.py`.

## Anthropic API usage

Lychee uses the Anthropic Messages API with tool use to produce
structured reviews.

**API call parameters:**

| Parameter | Value |
|-----------|-------|
| `max_tokens` | `4096` |
| `tool_choice` | `{"type": "tool", "name": "submit_review"}` |
| `tools` | `[submit_review]` (see schema below) |

**Tool schema (`submit_review`):**

The tool accepts a `ReviewResult` object with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `ripeness` | `str` | Merge readiness: `ripe`, `unripe`, or `sour` |
| `summary` | `str` | Nectar section (PR summary and assessment) |
| `walkthrough` | `str` | The Peel section (file-by-file walkthrough, Markdown) |
| `findings` | `list[Finding]` | Pits (individual findings) |
| `model` | `str` | Model identifier used for the review |
| `usage` | `object` | Token usage breakdown |

Each `Finding` contains:

| Field | Type | Description |
|-------|------|-------------|
| `file` | `str` | File path |
| `line` | `int\|null` | Line number (null if not line-specific) |
| `severity` | `str` | `info`, `minor`, `major`, or `critical` |
| `category` | `str` | `correctness`, `security`, `performance`, `tests`, `style`, `docs`, or `other` |
| `message` | `str` | Description of the finding |
| `suggestion` | `str\|null` | Suggested fix (optional) |

**Prompt caching:** The system prompt uses Anthropic's prompt caching
via ephemeral cache control blocks. The cached portion includes the
persona, rubric, severity definitions, and ripeness definitions. The
user message (PR-specific content) is not cached.

**Model selection:** Determined by context size and scope rules. See
`review.select_model()` in `src/lychee/review.py`.

**Retry behavior:** Retries on `RateLimitError`, `InternalServerError`,
and `APIConnectionError` with exponential backoff (default: 3 retries,
1s base delay, 60s max delay, with jitter).

Implementation: `src/lychee/claude.py`, `src/lychee/prompt.py`

## CLI interface

The `lychee` CLI provides a `review` command for running reviews from the
command line.

```
lychee review [OPTIONS]
```

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--dry-run` | flag | `false` | Run without API calls, using a fixture file |
| `--fixture PATH` | path | — | Path to a PR fixture JSON file (required with `--dry-run`) |
| `--pr REF` | string | — | PR reference in `owner/repo#number` format |
| `--post / --no-post` | flag | `true` | Post the review comment to GitHub |

**Environment variables required for live review:**
- `GITHUB_TOKEN`
- `ANTHROPIC_API_KEY`

**Examples:**

```bash
# Dry run with fixture
lychee review --dry-run --fixture tests/fixtures/pr_payload.json

# Live review, post to GitHub
lychee review --pr owner/repo#42

# Live review, print to stdout
lychee review --pr owner/repo#42 --no-post
```

Implementation: `src/lychee/__main__.py`
