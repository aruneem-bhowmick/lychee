# Canary Repository Setup

This guide explains how to set up a throwaway canary repository for
running the Lychee end-to-end test suite with real GitHub and Claude API
calls.

## 1. Create the canary repository

Create a new GitHub repository (e.g. `your-org/lychee-canary`). It can
be public or private. This repo is disposable and exists solely for e2e
testing.

## 2. Add a `.lychee.yml`

In the canary repo's default branch, add a `.lychee.yml` with default
configuration:

```yaml
model:
  default: "claude-sonnet-4-6"

review:
  max_files: 50
  severity_threshold: "info"
  tone: "balanced"
  language: "en"

features:
  cost_footer: true
```

## 3. Create a test branch and PR

1. Create a branch (e.g. `test/canary-pr`) from the default branch.
2. Add a small, reviewable code change — for example, a Python file with
   a few functions or a bug to detect.
3. Open a pull request from the test branch to the default branch.
4. Note the PR number for use with the e2e workflow.

## 4. Configure secrets in the Lychee repository

In the **Lychee** repository (not the canary), add the following Actions
secrets:

| Secret               | Description                                                     |
|----------------------|-----------------------------------------------------------------|
| `CANARY_GITHUB_TOKEN`| A PAT or fine-grained token with write access to the canary repo|
| `ANTHROPIC_API_KEY`  | An Anthropic API key for Claude calls                           |

The `CANARY_GITHUB_TOKEN` needs at minimum:
- **Repository permissions:** Contents (read), Pull requests (read/write),
  Issues (read/write) — issue comments are used for PR review comments.

## 5. Run the e2e workflow

Trigger the **E2E — Canary** workflow manually from the Lychee
repository's Actions tab:

1. Go to **Actions** → **E2E — Canary** → **Run workflow**.
2. Fill in the canary repo (e.g. `your-org/lychee-canary`).
3. Fill in the PR number (or `0` to auto-detect an open PR).
4. Click **Run workflow**.

The workflow installs Lychee, runs the gated e2e tests with a
600-second timeout, and reports results in the Actions log.

## 6. Verify results

After a successful run:

- The canary PR should have exactly one comment containing the
  `<!-- lychee:review -->` marker with Nectar, The Peel, and Pits
  sections.
- Re-running the workflow should update the existing comment in place
  without creating a duplicate.
- The comment should contain a `<!-- lychee:state {...} -->` marker at
  the end with the `last_reviewed_sha` matching the PR's head SHA.

## Notes

- Each e2e run consumes Claude API credits. Run only when validating
  the full pipeline.
- The canary repo is managed manually. There is no automation for
  creating or tearing it down.
- The e2e tests are excluded from default CI via the `-m 'not e2e'`
  pytest filter in `pyproject.toml`.
