# Roadmap

Project direction, design principles, and boundaries for Lychee.

## Current state

Lychee is a self-hosted, automated PR review tool powered by Claude. It
operates in two deployment modes:

- **CLI mode** runs as a GitHub Actions step. One-shot reviews triggered
  by PR events, no persistent infrastructure.
- **Server mode** runs as a GitHub App with a webhook server, async job
  queue, durable state, and health monitoring. Supports multiple
  repositories from a single deployment.

The review engine supports structured output (Nectar, Peel, Pits,
Ripeness), map-reduce for large PRs, triage classification, inline
comments, `@lychee` commands, scope-based configuration overrides, cost
tracking with budget caps, comment deduplication, and finding
fingerprinting.

## Design principles

**No-spam ergonomics.** Reviews update existing comments in place rather
than posting new ones. Each PR gets one review comment, identified by an
HTML marker and upserted on re-review. Inline comments are deduplicated
across pushes using content fingerprints.

**Predictable cost.** Every review reports its token usage and cost in
the comment footer. Budget caps halt reviews before exceeding a
configured spend limit. Triage classification routes trivial PRs to
cheaper models.

**Continuous extensibility.** The domain layer (`models.py`, `config.py`)
defines stable contracts. New features (commands, inline comments,
triage) are added behind feature flags without changing existing
behavior. Scope rules allow per-path and per-label configuration without
forking the config schema.

**Reproducible delivery.** Prompt construction and comment rendering are
pure functions. The review engine is deterministic given the same inputs
(modulo Claude's generation). Engine integrity is verified by hash checks
in CI.

## Non-goals

Lychee does not aim to be:

- **A multi-tenant SaaS platform.** Lychee is designed for self-hosted
  deployment. Each installation is operated by the repository owner.

- **A gatekeeper for merges.** Lychee posts reviews but never blocks CI,
  never gates merge, and never auto-approves PRs. Merge decisions remain
  with the team.

- **A replacement for linters, test runners, or static analysis.** Lychee
  provides high-level code review, not syntax checking or test execution.
  It complements existing CI tools rather than replacing them.

- **A code storage system.** PR diffs and file contents are held in memory
  during the review lifecycle and discarded afterward. Nothing is
  persisted beyond review metadata (SHA, comment ID, status).

- **An auditor of Anthropic API data handling.** How the Anthropic API
  processes and retains data sent to it is governed by Anthropic's terms
  and data policies, not by Lychee.

## Potential future directions

These are areas under consideration. None are commitments or scheduled
work.

- **Specialized review scopes.** Security-focused reviews, performance
  audits, or accessibility checks as distinct review modes with tailored
  prompts and rubrics.

- **Richer inline comment interactions.** Threaded replies on inline
  comments, follow-up suggestions, or iterative refinement based on
  author responses.

- **Custom review rubrics.** User-defined rubric files that replace or
  extend the default review categories and severity definitions.

- **Multi-model support.** Using models from multiple providers (not just
  Anthropic) for different review tasks or as fallback options.

- **Dashboard and analytics.** A web interface for viewing review
  history, finding trends, cost tracking across repositories, and
  reviewer effectiveness metrics.

## Known limitations

- **Single SQLite backend.** Server mode uses SQLite for state
  persistence. There is no pluggable database adapter for PostgreSQL or
  other backends. For most single-server deployments, SQLite is
  sufficient.

- **No secret scanning.** Lychee does not scan PR diffs for leaked
  credentials or secrets. Use dedicated secret scanning tools alongside
  Lychee.

- **Anthropic API dependency.** Reviews require a live connection to the
  Anthropic API. There is no offline mode or local model support.
