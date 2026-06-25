# Configuration

Lychee reads its configuration from `.lychee.yml` in the repository root.
All keys are optional and fall back to documented defaults. Unknown keys
at any nesting level are rejected at startup with a descriptive error
message.

If the file is missing entirely, Lychee runs with all defaults.

Implementation: `src/lychee/config.py`

## Schema reference

### `model`

Controls which Claude model is used for each review scenario.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default` | `str` | `claude-sonnet-4-6` | Model for standard reviews |
| `triage` | `str` | `claude-haiku-4-5-20251001` | Model for triage classification and trivial reviews |
| `large_pr` | `str` | `claude-opus-4-8` | Model for PRs exceeding 100,000 characters |

### `review`

Controls file filtering, size limits, output style, and budget.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `ignore_globs` | `list[str]` | `[]` | Glob patterns for files to exclude from review context |
| `max_files` | `int` | `50` | Maximum number of changed files to include. PRs exceeding this trigger map-reduce |
| `max_file_bytes` | `int` | `102400` | Maximum file size in bytes (100 KB). Larger files are skipped |
| `severity_threshold` | `str` | `info` | Minimum severity to include in output. One of: `info`, `minor`, `major`, `critical` |
| `tone` | `str` | `balanced` | Review tone. One of: `balanced`, `concise`, `detailed` |
| `language` | `str` | `en` | Language code for review output. Must be non-empty |
| `budget_cap_usd` | `float\|null` | `null` | Maximum spend per review in USD. `null` = no cap. Must be > 0 when set |
| `scope_rules` | `list[ScopeRule]` | `[]` | Per-path/per-label overrides. See [Scope rules](#scope-rules) |

### `features`

Feature flags that toggle optional capabilities.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `inline_comments` | `bool` | `false` | Post findings as inline review comments on specific diff lines |
| `cost_footer` | `bool` | `true` | Append token usage and cost breakdown to the review comment |
| `commands` | `bool` | `false` | Enable `@lychee` command handling in PR comments |
| `triage_pass` | `bool` | `false` | Run a cheap triage classification before the full review |

### `conventions_file`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `conventions_file` | `str\|null` | `null` | Path to a conventions file in the repository. Contents are appended to the system prompt |

### `authorization`

Controls which users can trigger `@lychee` commands.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `allowed_users` | `list[str]` | `[]` | GitHub logins permitted to use commands. Empty list = open access |

### `app`

Server-mode configuration. These fields are not used in CLI/Actions mode.
Required fields (`webhook_secret`, `app_id`, `private_key_path`) are
sourced from environment variables by the server entrypoint, not from
`.lychee.yml`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `webhook_secret` | `str` | (required) | HMAC secret for webhook signature verification |
| `app_id` | `int` | (required) | GitHub App ID |
| `private_key_path` | `str` | (required) | Path to the GitHub App private key PEM file |
| `queue_workers` | `int` | `4` | Number of async worker tasks |
| `queue_max_size` | `int` | `100` | Maximum queued jobs before rejecting with 503 |
| `state_backend` | `str` | `sqlite` | State persistence backend |
| `state_dsn` | `str` | `lychee_state.db` | Database connection string (file path for SQLite) |
| `host` | `str` | `0.0.0.0` | Server bind address |
| `port` | `int` | `8000` | Server bind port |

## Scope rules

Scope rules let you override review behavior for specific file paths
or PR labels. Rules are evaluated in declaration order; the first matching
rule wins.

Each rule can match on:
- `paths` — glob patterns against file paths (relative to repo root).
  Empty list matches all files.
- `labels` — PR label names. Empty list matches all PRs.

Both conditions must match for the rule to apply (AND logic). An empty
list in either field acts as a wildcard.

Available overrides per rule:

| Field | Type | Effect |
|-------|------|--------|
| `model` | `str\|null` | Override the Claude model for the review |
| `severity_threshold` | `str\|null` | Override the minimum severity for output |
| `tone` | `str\|null` | Override the review tone |
| `ignore` | `bool` | If `true`, exclude matching files from review entirely |

When a rule matches, only its non-null override fields take effect.
Unset fields fall back to the global `review.*` defaults.

When multiple files match different rules, the first file's matching rule
applies to the entire review run.

### Example: monorepo with scope rules

```yaml
review:
  scope_rules:
    # Skip generated files
    - paths: ["**/generated/**", "**/*.gen.ts"]
      ignore: true

    # Use a detailed tone for security-sensitive code
    - paths: ["src/auth/**", "src/crypto/**"]
      tone: detailed
      severity_threshold: info

    # Use Opus for infrastructure changes
    - paths: ["terraform/**", "k8s/**"]
      labels: ["infrastructure"]
      model: claude-opus-4-8

    # Concise reviews for documentation PRs
    - labels: ["docs"]
      tone: concise
      severity_threshold: major
```

## Environment variables

All secrets are sourced from environment variables. No secret field is
accepted in `.lychee.yml`.

| Variable | Required | Mode | Description |
|----------|----------|------|-------------|
| `GITHUB_TOKEN` | Yes (CLI) | CLI/Actions | GitHub API token with `contents:read` and `pull-requests:write` |
| `ANTHROPIC_API_KEY` | Yes | Both | Anthropic API key for Claude |
| `LYCHEE_WEBHOOK_SECRET` | Yes (server) | Server | HMAC secret for webhook verification |
| `LYCHEE_APP_ID` | Yes (server) | Server | GitHub App ID |
| `LYCHEE_PRIVATE_KEY_PATH` | Yes (server) | Server | Path to GitHub App private key PEM file |
| `LYCHEE_HOST` | No | Server | Server bind address (default: `0.0.0.0`) |
| `LYCHEE_PORT` | No | Server | Server bind port (default: `8000`) |
| `LYCHEE_QUEUE_WORKERS` | No | Server | Number of async workers (default: `4`) |
| `LYCHEE_QUEUE_MAX_SIZE` | No | Server | Maximum queued jobs (default: `100`) |
| `LYCHEE_STATE_BACKEND` | No | Server | State backend type (default: `sqlite`) |
| `LYCHEE_STATE_DSN` | No | Server | Database connection string (default: `lychee_state.db`) |

## Validation

Lychee validates the configuration at startup using Pydantic's strict
validation with `extra="forbid"`. This means:

- Unknown keys at any level produce an error naming the offending key.
- Type mismatches produce an error with the expected type and valid values
  (for enums/literals).
- Constraint violations (e.g. empty `language`, non-positive
  `budget_cap_usd`) produce an error with the constraint that was violated.

If validation fails, Lychee halts with a descriptive error message before
making any API calls.

## Example configurations

### Minimal

```yaml
model:
  default: claude-sonnet-4-6

review:
  severity_threshold: info

features:
  cost_footer: true
```

### Full-featured

```yaml
model:
  default: claude-sonnet-4-6
  triage: claude-haiku-4-5-20251001
  large_pr: claude-opus-4-8

review:
  ignore_globs:
    - "**/*.lock"
    - "**/*.min.js"
    - "vendor/**"
  max_files: 50
  max_file_bytes: 102400
  severity_threshold: info
  tone: balanced
  language: en
  budget_cap_usd: 0.50

features:
  inline_comments: true
  cost_footer: true
  commands: true
  triage_pass: true

conventions_file: .github/conventions.md

authorization:
  allowed_users:
    - maintainer-one
    - maintainer-two
```

### Budget-capped

```yaml
review:
  budget_cap_usd: 0.25
  severity_threshold: minor
  tone: concise

features:
  cost_footer: true
  triage_pass: true
```

When the review cost reaches the budget cap, Lychee stops and reports
the partial result with a budget-exceeded notice.
