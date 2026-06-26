<p align="center">
  <img src="assets/lychee-banner.svg" alt="Lychee Logo" width="550" />
  <br>
  <em>Peel back your pull requests.</em>
</p>

---

Lychee is an automated, Claude-powered pull request review engine. By directly parsing pull request diffs and metadata, Lychee constructs structured prompts and leverages Anthropic's Messages API (with native tool/schema enforcement, prompt caching, and token usage tracking) to generate highly contextual, structured feedback.

Designed to escape rate-limiting bottlenecks inherent in third-party hosted SaaS alternatives, Lychee processes pull requests in concurrent batches. The engine evaluates correctness, security, performance, test coverage, style, and documentation with a rigorous yet constructive tone, posting results back as a single, in-place updated pull request comment.

### Key Technical Capabilities
*   **Structured Schema Enforcement:** Ensures Claude outputs strictly adhere to a validation contract (`ReviewResult`) via custom tool definitions, producing structured summaries, file walkthroughs, and categorized findings.
*   **Smart Model Tiering:** Configurable routing rules triage simple changes to cheaper models (Haiku) while routing typical reviews to Sonnet and extremely large diffs (>100K characters) to Opus.
*   **Map-Reduce Review Pipeline:** Divides and summarizes large diffs exceeding file limits before generating final reviews to stay within token boundaries and maximize context relevancy.
*   **Deduplication & Fingerprinting:** Inline comments and findings are fingerprinted and matched across commit shas, preventing duplicate comment spam when files are updated.
*   **Cost Control & Budgeting:** Estimates and reports USD costs in comment footers and supports configurable run-budget caps.

---

## Deployment Modes

Lychee is designed as a decoupled architecture consisting of **Triggers**, a **Review Engine**, and **Sinks**, allowing it to be deployed in two modes:

1.  **CLI Mode (GitHub Actions):** Runs as a one-shot step in your GitHub Actions CI. Requires zero persistent server infrastructure.
2.  **Server Mode (GitHub App):** Runs as a long-lived, multi-repository GitHub App webhook server. Uses SQLite for state persistence, an asynchronous worker queue to manage concurrent workloads, and exposes health/metrics endpoints.

---

## Documentation Guide

Below is the directory of public-facing documentation files across the Lychee codebase, organized in a logical reading order.

### 1. Getting Started & Configuration
| Document | Path | Description |
| :--- | :--- | :--- |
| **Getting Started** | [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md) | Setup instructions for CLI mode and GitHub App mode. |
| **Configuration Schema** | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Reference for `.lychee.yml` settings, model routing, and scope rules. |
| **Interactive Commands** | [docs/COMMANDS.md](docs/COMMANDS.md) | Guide to triggering reviews via `@lychee` comments in pull requests. |

### 2. Architecture & Design Specifications
| Document | Path | Description |
| :--- | :--- | :--- |
| **Lychee Specification** | [docs-lychee/LYCHEE-SPEC.md](docs-lychee/LYCHEE-SPEC.md) | Authoritative product specification, domain contracts, and Agile delivery phases. |
| **Architecture Design** | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Detailed technical architecture, module layouts, and data flows. |
| **Glossary** | [docs/GLOSSARY.md](docs/GLOSSARY.md) | Technical concepts and branded terminologies mapped to code elements. |

### 3. Operations, Deployment & Security
| Document | Path | Description |
| :--- | :--- | :--- |
| **Production Deployment** | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Operational guidelines for hosting Lychee as a persistent GitHub App. |
| **Security & Credentials** | [docs/SECURITY.md](docs/SECURITY.md) | Authentication flows, webhook signature validation, and secrets handling. |
| **Canary Setup** | [docs/CANARY-SETUP.md](docs/CANARY-SETUP.md) | How to set up a throwaway repository for running end-to-end integration tests. |

### 4. Development & Project Trajectory
| Document | Path | Description |
| :--- | :--- | :--- |
| **Development Guidelines** | [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Guidelines for local setup, testing workflows, linting, and type check checks. |
| **Roadmap** | [docs/ROADMAP.md](docs/ROADMAP.md) | Current project milestones, core design principles, and boundaries. |