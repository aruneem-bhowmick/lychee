# Glossary

Branded terminology, technical concepts, and enumeration values used
throughout Lychee.

## Branded terms

These terms appear in user-facing output (review comments, command
responses) and throughout the codebase.

### Peel

As a verb: to run a review (`@lychee peel`). As a noun: the file-by-file
walkthrough section of a review comment ("The Peel"). Each changed file
gets a short note on what changed and whether anything looks problematic.

### Nectar

The summary section at the top of a review comment. A short paragraph
describing the PR's purpose and the overall assessment. Produced by the
`summary` field of `ReviewResult`.

### Pit

An individual finding in a review. Each pit identifies a file, optional
line number, severity, category, message, and optional code suggestion.
Represented by the `Finding` model. Pits are listed in the "Pits"
section of the review comment. Also called a "seed" in some contexts.

### Ripeness

The merge-readiness verdict for a PR. Displayed as a badge at the top
of the review comment:

- 🟢 **Ripe** — The PR looks ready to merge.
- 🟡 **Unripe** — There are issues that should be addressed first.
- 🔴 **Sour** — There are critical problems.

### Cluster mode

Concurrent multi-PR review. The server's worker pool processes multiple
PR reviews simultaneously through the async job queue.

### "Tough shell, sweet flesh"

The reviewer persona description used in the system prompt. Reviews are
thorough and direct (tough shell) but constructive and specific (sweet
flesh).

## Technical terms

### Finding

A single review observation. Defined by the `Finding` model in
`src/lychee/models.py`:

- `file` — file path
- `line` — line number (optional)
- `severity` — `info`, `minor`, `major`, or `critical`
- `category` — `correctness`, `security`, `performance`, `tests`,
  `style`, `docs`, or `other`
- `message` — description of the issue
- `suggestion` — proposed fix (optional)

### ReviewResult

The structured output from the review engine. Defined in
`src/lychee/models.py`:

- `ripeness` — merge-readiness verdict
- `summary` — Nectar section text
- `walkthrough` — The Peel section (Markdown)
- `findings` — list of Pits
- `model` — Claude model identifier used
- `usage` — token usage breakdown

### Scope rule

A per-path or per-label configuration override in `.lychee.yml`. Rules
are evaluated in declaration order; first match wins. A scope rule can
override the review model, severity threshold, tone, or skip files
entirely. See [CONFIGURATION.md](CONFIGURATION.md#scope-rules).

### Map-reduce

The review strategy for large PRs. When a PR exceeds `review.max_files`
(default 50), the engine partitions files into groups of 10, reviews
each group separately (map phase), then merges the partial results into
a single review (reduce phase). See
[ARCHITECTURE.md](ARCHITECTURE.md#map-reduce-for-large-prs).

### Triage pass

An optional cheap pre-classification step. When `features.triage_pass`
is enabled, Lychee sends the PR context to a fast model (Haiku) to
classify the PR as `trivial` or `substantive`. Trivial PRs receive a
lightweight review; substantive PRs go through the full pipeline.

### State marker

An HTML comment embedded at the end of review comments for tracking:
`<!-- lychee:state {"last_reviewed_sha": "abc123", ...} -->`. Used to
track the last reviewed commit SHA and enable comment upsert on
re-review.

### Review marker

The HTML comment `<!-- lychee:review -->` embedded in review comments.
Used by the poster to locate the existing comment for upsert. Prevents
duplicate comments on re-review.

### Position map

A mapping from file path and line number to GitHub diff position. Built
by parsing the unified diff and tracking hunk offsets. Used to place
inline review comments on the correct line in the GitHub diff view.

Implementation: `src/lychee/diff_mapping.py`

### Fingerprint

A SHA-256 hash of a finding's key attributes (file, line, severity,
first 12 hex characters of the message hash). Used for cross-push
deduplication — findings that were already posted in a previous review
are not posted again as inline comments.

Implementation: `src/lychee/dedup.py`

## Severity levels

Defined as `Severity` (StrEnum) in `src/lychee/models.py`:

| Level | Meaning |
|-------|---------|
| `info` | Observation or suggestion, no action required |
| `minor` | Small issue worth noting, low impact |
| `major` | Significant issue that should be addressed |
| `critical` | Serious problem that must be fixed before merge |

Severity ordering: `critical` > `major` > `minor` > `info`. The
`review.severity_threshold` config controls the minimum severity
included in the review output.

## Categories

Defined as `Category` (StrEnum) in `src/lychee/models.py`:

| Category | Scope |
|----------|-------|
| `correctness` | Logic errors, bugs, incorrect behavior |
| `security` | Vulnerabilities, unsafe patterns |
| `performance` | Inefficiencies, scaling concerns |
| `tests` | Missing or inadequate test coverage |
| `style` | Code style, readability, naming |
| `docs` | Missing or inaccurate documentation |
| `other` | Anything not covered by the above |

## Ripeness verdicts

Defined as `Ripeness` (StrEnum) in `src/lychee/models.py`:

| Verdict | Badge | Meaning |
|---------|-------|---------|
| `ripe` | 🟢 **Ripe** | PR is ready to merge |
| `unripe` | 🟡 **Unripe** | PR has issues that need attention |
| `sour` | 🔴 **Sour** | PR has critical problems |
