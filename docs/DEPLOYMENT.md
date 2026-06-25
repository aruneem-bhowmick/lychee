# Deployment

Lychee supports two deployment modes: GitHub Actions (CLI mode) and
GitHub App (server mode). This guide covers production setup for both.

## GitHub Actions deployment

Run Lychee as a workflow step in your repository's CI. No server
infrastructure required.

### Workflow file

Create `.github/workflows/lychee-review.yml`:

```yaml
name: Lychee PR Review

on:
  pull_request:
    types: [opened, synchronize, reopened]
  issue_comment:
    types: [created]

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    if: >-
      (github.event_name == 'pull_request' &&
       github.event.pull_request.head.repo.full_name == github.repository &&
       secrets.ANTHROPIC_API_KEY != '') ||
      (github.event_name == 'issue_comment' &&
       github.event.issue.pull_request &&
       contains(github.event.comment.body, '@lychee') &&
       secrets.ANTHROPIC_API_KEY != '')
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e .
      - run: python scripts/run_action.py
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

### Required secrets

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude calls |

`GITHUB_TOKEN` is provided automatically by GitHub Actions with the
permissions declared in the workflow (`contents: read`,
`pull-requests: write`).

### Fork PR protection

The workflow condition
`github.event.pull_request.head.repo.full_name == github.repository`
blocks fork PRs from triggering the review. Fork branches would
otherwise have access to the repository's secrets. This condition is
evaluated before any step executes.

### Re-review on push

When a PR receives new commits (the `synchronize` action), Lychee
locates its existing review comment by the `<!-- lychee:review -->` HTML
marker and updates it in place. No duplicate comments are created.

### Command handling in Actions mode

The `issue_comment` trigger handles `@lychee` commands. The workflow
condition checks three things: the event is a comment, the comment is on
a PR (not a standalone issue), and the body contains `@lychee`. The
`run_action.py` script dispatches the command to the appropriate handler.

See [COMMANDS.md](COMMANDS.md) for command details.

## GitHub App deployment

Run Lychee as a persistent server that receives webhook events from
GitHub. Supports multiple repositories, async job queuing, durable state
tracking, and health monitoring.

### 1. Register a GitHub App

Create a GitHub App at `https://github.com/settings/apps/new` with:

**Permissions:**
- Repository permissions: Contents (Read), Pull requests (Read & Write),
  Issues (Read & Write)
- Subscribe to events: Pull request, Issue comment

**Webhook URL:** `https://your-host:8000/webhook`

After creation, note the App ID and generate a private key (PEM file).

### 2. Configure environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LYCHEE_WEBHOOK_SECRET` | Yes | — | Webhook secret from App settings |
| `LYCHEE_APP_ID` | Yes | — | GitHub App ID |
| `LYCHEE_PRIVATE_KEY_PATH` | Yes | — | Path to the private key PEM file |
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key |
| `LYCHEE_HOST` | No | `0.0.0.0` | Server bind address |
| `LYCHEE_PORT` | No | `8000` | Server bind port |
| `LYCHEE_QUEUE_WORKERS` | No | `4` | Number of async worker tasks |
| `LYCHEE_QUEUE_MAX_SIZE` | No | `100` | Maximum queued jobs |
| `LYCHEE_STATE_BACKEND` | No | `sqlite` | State persistence backend |
| `LYCHEE_STATE_DSN` | No | `lychee_state.db` | Database path |

### 3. Docker deployment

Build and run the container:

```bash
docker build -t lychee .
docker run -d \
  -p 8000:8000 \
  -e LYCHEE_WEBHOOK_SECRET="your-secret" \
  -e LYCHEE_APP_ID="12345" \
  -e LYCHEE_PRIVATE_KEY_PATH="/app/private-key.pem" \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  -v /path/to/private-key.pem:/app/private-key.pem:ro \
  -v /path/to/data:/app/data \
  lychee
```

The Dockerfile is based on `python:3.11-slim`, installs Lychee, exposes
port 8000, and runs `python -m scripts.run_server`.

**Built-in health check:** The Docker `HEALTHCHECK` instruction probes
`http://localhost:8000/health` every 30 seconds with a 5-second timeout,
10-second start period, and 3 retries before marking the container
unhealthy.

### 4. Running without Docker

Run the server directly with uvicorn:

```bash
export LYCHEE_WEBHOOK_SECRET="your-secret"
export LYCHEE_APP_ID="12345"
export LYCHEE_PRIVATE_KEY_PATH="/path/to/private-key.pem"
export ANTHROPIC_API_KEY="sk-ant-..."

python -m scripts.run_server
```

The server binds to `LYCHEE_HOST:LYCHEE_PORT` (default `0.0.0.0:8000`).

### 5. State persistence

Server mode stores review state (last reviewed SHA, comment ID) and
installation metadata in SQLite. The database file is created at the
`LYCHEE_STATE_DSN` path (default: `lychee_state.db` in the working
directory).

For Docker deployments, mount a volume for the database file to persist
state across container restarts:

```bash
-e LYCHEE_STATE_DSN="/app/data/lychee_state.db"
-v /path/to/data:/app/data
```

Back up the SQLite file periodically. The file uses WAL mode and
supports concurrent reads.

### 6. Worker pool sizing

The `LYCHEE_QUEUE_WORKERS` setting controls how many reviews can run
concurrently. Each worker processes one job at a time (one Claude API
call sequence). Sizing considerations:

- Each review makes 1-3 Claude API calls (triage + review, or
  map-reduce with multiple calls).
- Workers are async tasks, not OS threads. Memory overhead per worker
  is low.
- The limiting factor is Anthropic API rate limits, not local compute.
- Start with the default (4 workers) and adjust based on queue depth
  observed in `/metrics`.

### 7. Health monitoring

**Health check:** `GET /health` returns `200` when the server, state
store, and worker pool are all operational. Returns `503` otherwise.
Use this endpoint for load balancer health probes and container
orchestration.

**Metrics:** `GET /metrics` returns a JSON snapshot of runtime metrics:
uptime, queue depth, worker status, and job counts. Use this endpoint
for monitoring dashboards and alerting.

See [API-REFERENCE.md](API-REFERENCE.md) for response schemas.

### 8. Graceful shutdown

On receiving a shutdown signal (SIGTERM, SIGINT), the server:

1. Stops accepting new webhook events.
2. Drains the worker pool with a 30-second timeout. Workers finish their
   current job but do not pick up new ones.
3. Closes the state store connection.

Jobs that do not complete within the drain timeout are abandoned. GitHub
will redeliver the webhook event, and the next server start will process
it.

## Container registry

The Deploy workflow (`.github/workflows/deploy.yml`) builds a Docker
image and pushes it to `ghcr.io`. It triggers on:

- Manual dispatch (`workflow_dispatch`) with an optional tag override.
- Tag pushes matching `v*.*.*` for release deployments.

Image tags include the semver version, major.minor, and the git SHA.
The workflow uses GitHub Actions cache for Docker layer caching.

The deploy job is a placeholder — replace it with your actual deployment
mechanism (kubectl, ECS, Cloud Run, etc.).

## Security hardening

See [SECURITY.md](SECURITY.md) for the full security model, credential
handling, threat boundaries, and operational hardening checklist.
