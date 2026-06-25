# Commands

Lychee supports interactive commands via PR comments. Comment `@lychee`
followed by a command name on any pull request to trigger a targeted
review action.

Commands require `features.commands: true` in `.lychee.yml` (disabled by
default).

## Available commands

| Command | Description | Output |
|---------|-------------|--------|
| `@lychee peel` | Full review | Nectar (summary) + The Peel (walkthrough) + Pits (findings) |
| `@lychee juice` | Summary only | Nectar section |
| `@lychee pit` | Highest-severity finding | Single most critical finding |
| `@lychee ripe?` | Merge-readiness check | Ripeness verdict only |

### `peel`

Runs a full review and posts the complete output: summary, file-by-file
walkthrough, and all findings above the configured severity threshold.
Equivalent to the automatic review triggered on PR events, but invoked
on demand.

### `juice`

Runs a full review but only posts the Nectar section — a short summary
of the PR's purpose and overall assessment. Useful for a quick read
without the detail of individual findings.

### `pit`

Runs a full review and posts only the single highest-severity finding.
If multiple findings share the highest severity, the first one is
returned. Useful for quickly identifying the most critical issue.

### `ripe?`

Runs a full review and posts only the Ripeness verdict: whether the PR
is ripe (ready to merge), unripe (needs work), or sour (critical
issues). No findings or walkthrough are included.

## Unknown commands

If the comment body contains `@lychee` followed by an unrecognized
command, Lychee responds with a help message listing the four available
commands and their descriptions.

## Authorization

Command access is controlled by `authorization.allowed_users` in
`.lychee.yml`:

- **Empty list (default):** All users can run commands.
- **Populated list:** Only listed GitHub logins can run commands.
  Matching is case-insensitive.
- **Unauthorized users:** Receive a refusal comment that names the user
  but does not reveal the allowed list.

Authorization runs after command parsing but before the review engine.
Unauthorized commands never trigger API calls to Claude or GitHub beyond
posting the refusal.

Implementation: `src/lychee/authorization.py`

### Example configuration

```yaml
features:
  commands: true

authorization:
  allowed_users:
    - alice
    - bob
```

## Interaction with other settings

Commands respect the same configuration as automatic reviews:

- **`review.severity_threshold`** — Filters findings in `peel` output.
- **`review.tone`** — Controls review tone (`balanced`, `concise`,
  `detailed`).
- **`review.scope_rules`** — Per-path and per-label overrides apply to
  command-triggered reviews.
- **`features.inline_comments`** — When enabled, `peel` also posts
  inline review comments.
- **`features.cost_footer`** — When enabled, `peel` appends the cost
  breakdown.

## Processing flow

1. **Parse** — `commands.parse_command()` extracts the command from the
   comment body. Returns `None` if the comment does not mention
   `@lychee`, or `UnknownCommand` for unrecognized commands.

2. **Authorize** — `authorization.is_authorized()` checks the commenter's
   login against the `allowed_users` list. If unauthorized,
   `format_refusal()` generates the refusal text and the pipeline stops.

3. **Review** — The review engine runs a full review (same pipeline as
   automatic reviews: context fetch, prompt build, Claude API call).

4. **Render** — `command_render.py` maps the command to a renderer that
   extracts the relevant section from the `ReviewResult`. Each command
   has its own renderer function (`render_peel_response`,
   `render_juice_response`, `render_pit_response`,
   `render_ripe_response`).

5. **Post** — The rendered response is posted as an issue comment on the
   PR. Command responses are separate comments, not upserted into the
   main review comment.

Implementation: `src/lychee/commands.py`, `src/lychee/command_render.py`,
`src/lychee/queue.py` (server mode dispatching).
