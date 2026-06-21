# Security

Lychee's security model, credential handling, threat boundaries, and operational guidance for both deployment modes: the GitHub Actions CLI and the GitHub App server.

## Reporting vulnerabilities

If you find a security issue, report it privately. Do not open a public GitHub issue.

Email the maintainers directly or use GitHub's private vulnerability reporting (Security tab > Report a vulnerability). Include a description of the issue, reproduction steps, and the affected component. We will acknowledge receipt within 48 hours and provide a fix timeline within 7 days.

## Architecture overview

Lychee operates in two modes:

**CLI mode** runs as a GitHub Actions step inside the repository's own CI. The action reads the PR event payload, fetches context from GitHub, sends it to Claude for review, and posts the result as a PR comment. Credentials come from the Actions environment (`GITHUB_TOKEN`, `ANTHROPIC_API_KEY`). No persistent state, no long-lived server, no inbound network connections.

**Server mode** runs as a GitHub App behind a webhook endpoint. GitHub POSTs signed events to the server, which verifies them, enqueues jobs, and processes reviews through an async worker pool. Authentication uses GitHub App JWTs and installation tokens. State persists in SQLite. The server exposes three HTTP routes: `/webhook` (POST), `/health` (GET), and `/metrics` (GET).

Both modes access the same data: PR diffs, file contents (up to 100 KB per file, max 50 files by default), PR metadata, and commit messages. Both send that context to the Anthropic API and post the review back to GitHub.

## Authentication and authorization

### GitHub App authentication (server mode)

The server authenticates to GitHub using the standard App JWT flow:

1. An RSA private key (PEM format) is loaded from a file path specified by `LYCHEE_PRIVATE_KEY_PATH`. The key is read once at startup and held in memory. It is never logged, never transmitted, and never written to disk by the application.
2. A JWT is generated with RS256 signing, a 10-minute expiry (`exp`), and a 60-second `iat` backdate to tolerate clock skew between the server and GitHub.
3. The JWT is exchanged for a short-lived installation access token via `POST /app/installations/{id}/access_tokens`.
4. Installation tokens are cached in memory, keyed by installation ID. Tokens are refreshed when they are within 5 minutes of expiry. No token persists across process restarts.

See `src/lychee/app_auth.py`. `AppAuthenticator` manages JWT generation, token exchange, and caching. Failures raise `AppAuthError` with an optional HTTP status code.

### GitHub Actions authentication (CLI mode)

In CLI mode, credentials come from the GitHub Actions environment:

- `GITHUB_TOKEN` is the workflow-scoped token provided by Actions. The workflow requests least-privilege permissions: `contents: read` and `pull-requests: write`.
- `ANTHROPIC_API_KEY` is stored as a repository secret and injected via `env:` in the workflow step.

Fork PRs are blocked by an explicit condition in the workflow: `github.event.pull_request.head.repo.full_name == github.repository`. This prevents fork branches from running the review action, which would have access to the repository's secrets. The condition is evaluated before any step executes.

### Command authorization

When users comment `@lychee` commands on a PR, Lychee checks the commenter's GitHub login against `authorization.allowed_users` in `.lychee.yml`. The comparison is case-insensitive (GitHub logins are case-insensitive). If the list is empty, commands are open to all users. If the list is populated, unauthorized users receive a refusal comment that names the user but does not reveal the allowed list.

Authorization runs after parsing but before the review engine, so unauthorized commands never trigger API calls to Claude or GitHub.

Implementation: `src/lychee/authorization.py`.

## Webhook security

The webhook endpoint (`/webhook`) verifies every incoming request using HMAC-SHA256:

1. The raw request body and the `X-Hub-Signature-256` header value are passed to `verify_signature()`.
2. The server computes `HMAC-SHA256(webhook_secret, body)` and compares it against the header value using `hmac.compare_digest()` (constant-time comparison, resistant to timing attacks).
3. Requests with missing, malformed, or invalid signatures are rejected with HTTP 403.
4. Non-applicable events (events Lychee does not act on) return HTTP 200 and are silently discarded. This prevents information leakage about which events the server handles.
5. When the job queue is full, the server returns HTTP 503 so GitHub backs off and retries.

The webhook secret is configured via the `LYCHEE_WEBHOOK_SECRET` environment variable. It is never logged.

See `src/lychee/webhook.py`.

## Credential handling

All secrets are sourced from environment variables or file paths. No secret is accepted in `.lychee.yml` or any other configuration file checked into source control.

| Secret | Source | Scope |
|---|---|---|
| `GITHUB_TOKEN` | GitHub Actions environment | Per-workflow run |
| `ANTHROPIC_API_KEY` | Environment variable | Server lifetime or single action run |
| `LYCHEE_WEBHOOK_SECRET` | Environment variable | Server lifetime |
| `LYCHEE_PRIVATE_KEY_PATH` | File path (env var) | Server lifetime (key loaded at startup) |
| `LYCHEE_APP_ID` | Environment variable | Server lifetime |

**What is never logged:** API keys, tokens, webhook secrets, private key contents, JWT values, and installation token values. The structured JSON logging formatter in `src/lychee/observability.py` emits correlation IDs, timestamps, module names, and log levels. Secrets are excluded by design: they are never passed to logging calls.

**What is logged:** Repository name, PR number, head SHA, model name, token usage counts, cost in USD, review strategy, triage verdict, finding counts by severity, and wall-clock duration. No PR content (titles, bodies, diffs, file contents) appears in log output.

## Data handling

### What Lychee reads

- PR metadata: repository name, PR number, author, labels, base/head SHAs
- PR diff (unified diff format)
- Changed file contents (up to `review.max_file_bytes`, default 100 KB per file)
- Commit messages
- PR comments (for command parsing)
- Optional conventions file (`.lychee-conventions` or configured path)

### What Lychee sends to the Anthropic API

The full review context (PR metadata, diff, file contents, commit messages) is sent to Claude as a structured prompt. This is the core function of the tool: AI-powered code review requires the model to see the code.

If your organization has data residency or confidentiality requirements that prevent sending source code to external APIs, Lychee is not suitable for those repositories. Consider using `review.ignore_globs` and scope rules to exclude sensitive files from the review context.

### What Lychee writes

- PR comments (review results, command responses, refusal messages)
- SQLite state records (server mode): repository name, PR number, installation ID, review status, last-reviewed SHA, comment ID, and timestamps. No code content is stored.
- Structured log output to stdout/stderr

### What Lychee does not store

Lychee does not maintain a copy of source code, diffs, or PR content beyond the lifetime of a single review run. In CLI mode, data lives only in process memory for the duration of the action. In server mode, the SQLite state store tracks review metadata (which PRs were reviewed, their status, the last SHA) but not the code itself.

## Configuration validation

`.lychee.yml` is validated using Pydantic v2 with `extra="forbid"` on every model at every nesting level. Unknown keys at any depth produce a descriptive error naming the offending key. This prevents typos from silently creating unvalidated configuration and blocks injection of unexpected fields.

Type constraints, enum validation, and custom validators (e.g., `budget_cap_usd` must be positive when set, `language` must be non-empty) are enforced at load time. Invalid configuration halts startup.

See `src/lychee/config.py`.

## Rate limiting and cost controls

### Rate limiting

`src/lychee/rate_limiter.py` provides a token-bucket rate limiter with configurable capacity and refill rate. Pre-configured tiers range from 5 requests/second (tier 1) to 50 requests/second (tier 4).

The retry wrapper handles transient Anthropic API errors (429, 500, 529, connection errors) with exponential backoff and optional jitter. Non-retryable errors (401, 400) propagate immediately. `Retry-After` headers from rate limit responses are respected.

### Budget caps

The `review.budget_cap_usd` configuration field sets a per-review spending limit. The review engine checks cumulative cost after each Claude API call (including each map-reduce partition). If the cap is exceeded, `BudgetExceededError` is raised, an abort comment is posted to the PR, and the review terminates.

Cost tracking uses a per-model pricing table with distinct rates for input, output, and cached-input tokens. Unknown models fall back to Sonnet pricing with a logged warning.

### Queue backpressure

The job queue (server mode) has a configurable maximum size (default 100). When the queue is full, the webhook handler returns HTTP 503, which signals GitHub to back off and retry. This prevents unbounded memory growth from event floods.

## Deployment security

### Docker

The `Dockerfile` uses `python:3.11-slim` as its base image. No secrets are baked into the image. All credentials are injected at runtime via environment variables.

The health check probes `/health` every 30 seconds. The `/health` endpoint checks state store connectivity and worker pool liveness. The `/metrics` endpoint exposes runtime metrics (uptime, queue depth, active workers, job counts). Neither endpoint exposes secrets or review content.

### GitHub App permissions

The GitHub App requires these permissions:

- **Repository contents**: read (to fetch diffs and file contents)
- **Pull requests**: read and write (to read PR metadata and post review comments)
- **Issues**: read and write (to read and post issue comments for commands)

Request only these permissions when configuring the App. The App subscribes to `pull_request` and `issue_comment` webhook events.

### Network exposure

In server mode, the webhook endpoint must be reachable from GitHub's webhook delivery IPs. Restrict inbound access to GitHub's published IP ranges where possible. The `/health` and `/metrics` endpoints are informational and should not be exposed to the public internet in production.

In CLI mode, no inbound network access is required. The action makes outbound HTTPS connections to the GitHub API and the Anthropic API.

## Supply chain

Runtime dependencies are pinned to minimum versions in `pyproject.toml`:

| Dependency | Purpose |
|---|---|
| `anthropic` | Claude API client |
| `PyGithub` | GitHub API client |
| `PyYAML` | Configuration file parsing |
| `pydantic` | Configuration and model validation |
| `click` | CLI interface |
| `httpx` | Async HTTP client (App auth token exchange) |
| `starlette` | ASGI web framework (webhook server) |
| `uvicorn` | ASGI server |
| `PyJWT` | JWT generation for GitHub App auth |
| `cryptography` | RSA key handling for JWT signing |
| `aiosqlite` | Async SQLite driver (state store) |

Development dependencies (testing, linting, type-checking) are isolated under the `[dev]` extra and are not installed in production images.

## Code quality gates

These checks run on every PR and block merging on failure:

- **Ruff**: linter (style, import ordering, common errors)
- **Black**: code formatter (deterministic output)
- **Mypy**: strict mode type checking (no untyped definitions, no implicit optionals)
- **pytest**: 80% minimum coverage threshold (`--cov-fail-under=80`)
- **Engine integrity**: SHA-256 hash verification of engine module source files and public API surface checks, run as a separate CI job

Pre-commit hooks enforce Ruff, Black, and MyPy locally before commits reach CI.

## Threat model

### Trusted inputs

- `.lychee.yml` (repository owner controls this)
- Environment variables set by the deployer
- GitHub App private key (deployer controls access)

### Untrusted inputs

- **Webhook payloads**: Authenticated via HMAC-SHA256 signature verification. Payloads with invalid signatures are rejected before parsing.
- **PR content (diffs, file contents, comments)**: This is user-generated content from PR authors and commenters. Lychee passes it to Claude as prompt input and posts Claude's output as PR comments. The review output is markdown rendered by GitHub's own sanitization layer. Lychee does not execute any code from PRs, render HTML directly, or interpret PR content as commands (beyond the `@lychee` mention parser, which uses a fixed enum of known commands).
- **Claude API responses**: Parsed through Pydantic validation with `extra="forbid"`. Unexpected fields, missing fields, and type mismatches raise `ClaudeReviewError`. The response is rendered as markdown and posted as a PR comment.

### Out of scope

- **Secrets in PR diffs**: If a PR diff contains secrets (API keys, passwords, etc.), those secrets will be sent to the Anthropic API as part of the review context. Lychee does not scan for or redact secrets in PR content. Use a pre-commit hook or CI step (e.g., `truffleHog`, `gitleaks`, `detect-secrets`) to prevent secrets from reaching PRs in the first place.
- **Anthropic API data handling**: How Anthropic stores, processes, or retains the data sent to its API is governed by Anthropic's terms of service and data processing agreements. Review Anthropic's policies independently.
- **GitHub data handling**: PR content, comments, and metadata are stored and processed by GitHub per their terms of service.
- **Denial of service via large PRs**: Lychee enforces `max_files` (default 50) and `max_file_bytes` (default 100 KB) limits, and the queue has a configurable max size. These limits bound resource consumption but do not prevent a determined actor from submitting many PRs that individually fall within limits.

## Hardening checklist

For production deployments of the GitHub App server:

- [ ] Use a strong, random webhook secret (at least 32 characters)
- [ ] Store the RSA private key outside the container image; mount it as a read-only volume or inject via a secrets manager
- [ ] Restrict the `/health` and `/metrics` endpoints to internal networks
- [ ] Set `review.budget_cap_usd` to prevent runaway API costs
- [ ] Populate `authorization.allowed_users` if command access should be restricted
- [ ] Pin the Docker base image to a specific digest for reproducible builds
- [ ] Run the container as a non-root user
- [ ] Restrict inbound traffic to GitHub's webhook delivery IP ranges
- [ ] Rotate the webhook secret and private key periodically
- [ ] Monitor structured log output for `review_failed` events and authentication errors
- [ ] Review Anthropic's data retention and processing policies for your compliance requirements
