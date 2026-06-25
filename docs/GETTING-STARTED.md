# Getting Started

Set up Lychee for automated PR reviews. This guide covers both deployment
modes: running as a GitHub Actions step (CLI mode) and running as a
standalone GitHub App server.

## Prerequisites

- Python 3.11 or later
- A GitHub personal access token or GitHub App installation
- An Anthropic API key with access to Claude

## Installation

Clone the repository and install in editable mode:

```bash
git clone https://github.com/aspect-analytics/lychee.git
cd lychee
pip install -e .
```

For development dependencies (linting, testing, type checking), install the
dev extras:

```bash
pip install -e ".[dev]"
```

The installation creates a `lychee` CLI entry point.

## Configuration

Create a `.lychee.yml` file in your repository root. A minimal configuration:

```yaml
model:
  default: claude-sonnet-4-6

review:
  severity_threshold: info
  tone: balanced

features:
  cost_footer: true
```

All configuration keys have sensible defaults. Unknown keys are rejected at
startup with a descriptive error. See [CONFIGURATION.md](CONFIGURATION.md)
for the full schema reference.

## CLI mode

CLI mode runs a one-shot review from the command line. Useful for local
testing and CI pipelines.

### Dry-run with a fixture

Run a review against a saved PR fixture without making any API calls:

```bash
lychee review --dry-run --fixture tests/fixtures/pr_payload.json
```

This loads the fixture, builds prompts, and prints the rendered review
comment to stdout. No GitHub or Claude API calls are made.

### Live review

Review a real pull request:

```bash
export GITHUB_TOKEN="ghp_..."
export ANTHROPIC_API_KEY="sk-ant-..."

lychee review --pr owner/repo#42
```

This fetches the PR context from GitHub, sends it to Claude for review, and
posts the result as a PR comment. Use `--no-post` to print the comment
without posting it:

```bash
lychee review --pr owner/repo#42 --no-post
```

## GitHub Actions mode

Add Lychee as a workflow step that runs on every PR event.

### Workflow setup

Create `.github/workflows/lychee-review.yml`:

```yaml
name: Lychee Review

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
      github.event_name == 'pull_request' &&
      github.event.pull_request.head.repo.full_name == github.repository
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install .
      - run: python -m scripts.run_action
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

### Required secrets

| Secret             | Description                          |
|--------------------|--------------------------------------|
| `ANTHROPIC_API_KEY`| Anthropic API key for Claude calls   |

`GITHUB_TOKEN` is provided automatically by GitHub Actions with the
permissions declared in the workflow.

### Fork PR protection

The workflow condition
`github.event.pull_request.head.repo.full_name == github.repository`
prevents the review from running on fork PRs. Fork branches would otherwise
have access to the repository's secrets.

### Re-review on push

When a PR receives new commits (`synchronize` event), Lychee updates its
existing comment in place rather than posting a new one. The comment is
located by the `<!-- lychee:review -->` HTML marker.

### Command handling

To handle `@lychee` commands in Actions mode, add the `issue_comment`
trigger and a second job:

```yaml
  command:
    runs-on: ubuntu-latest
    if: >-
      github.event_name == 'issue_comment' &&
      github.event.issue.pull_request &&
      contains(github.event.comment.body, '@lychee')
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install .
      - run: python -m scripts.run_action
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

See [COMMANDS.md](COMMANDS.md) for the full command reference.

## GitHub App mode

For multi-repository deployments, run Lychee as a GitHub App with a
persistent webhook server. This mode supports async job queuing, durable
state tracking, and health monitoring.

See [DEPLOYMENT.md](DEPLOYMENT.md) for full App setup instructions.

## Understanding the output

A Lychee review comment has four sections:

**Nectar** is the summary at the top. A short paragraph describing the PR's
purpose and the overall assessment.

**The Peel** is the file-by-file walkthrough. Each changed file gets a
brief note on what changed and whether anything looks problematic.

**Pits** are the individual findings. Each pit has a severity level
(`info`, `minor`, `major`, `critical`), a category (`correctness`,
`security`, `performance`, `tests`, `style`, `docs`, `other`), and a
concrete message with an optional code suggestion.

**Ripeness** is the merge-readiness verdict at the top of the comment:

- **Ripe** means the PR looks ready to merge.
- **Unripe** means there are issues that should be addressed first.
- **Sour** means there are critical problems.

See [GLOSSARY.md](GLOSSARY.md) for the full terminology reference.

## Next steps

- [CONFIGURATION.md](CONFIGURATION.md) — full `.lychee.yml` schema reference
- [COMMANDS.md](COMMANDS.md) — `@lychee` command interface
- [DEPLOYMENT.md](DEPLOYMENT.md) — production deployment guide
- [ARCHITECTURE.md](ARCHITECTURE.md) — system design and data flow
