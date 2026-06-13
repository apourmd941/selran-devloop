# Tag Vocabulary

Controlled vocabulary for tags applied to files (in `structure.json`) and functions (in `functions.json`). Using a controlled vocabulary keeps the codemap useful for downstream skills — `app-audit` can query "all files with tag `security-sensitive`" and get a reliable answer.

If a file or function genuinely needs a tag not in this list, add it — but prefer reusing the existing tags. Adding new tags should be the exception.

---

## Domain tags — what the code is *about*

Files and functions can have multiple domain tags.

- `auth` — authentication, login, session management
- `authz` — authorization, permissions, access control (distinct from `auth`)
- `db` — direct database interaction (queries, migrations, schema)
- `cache` — caching layer, memoization
- `worker` — background job, queue consumer, scheduled task
- `api` — HTTP / RPC endpoint handler, route definition
- `client` — HTTP / RPC client code that calls external services
- `ui` — user-facing UI component, view, page
- `state` — client-side or app-wide state management
- `router` — routing / navigation logic
- `data-model` — domain model definitions (types, schemas, ORM models)
- `validation` — input validation, schema enforcement
- `serialization` — encoding / decoding (JSON, MessagePack, protobuf, etc.)
- `migration` — database schema migrations or data migrations
- `config` — configuration loading, environment handling
- `logging` — logging utilities, log formatting
- `metrics` — metrics, telemetry, observability
- `error-handling` — error types, error formatting, error reporting
- `email` — email sending, parsing, threading
- `file-io` — file system reads/writes (non-config)
- `network` — low-level networking concerns
- `crypto` — cryptography, hashing, signing (not auth specifically)
- `ipc` — inter-process communication
- `embedding` — vector embedding generation or storage
- `search` — search indexing or query
- `ml` — machine learning model loading, inference
- `parsing` — parsing of non-trivial formats (text, files, protocols)

---

## Concern tags — *what's special about this code*

These are orthogonal to domain. A function can be `auth` (domain) and `security-sensitive` (concern) and `async` (technical).

- `security-sensitive` — handles credentials, tokens, PII, or secrets. Audit's category 3 queries this tag.
- `concurrency` — uses locking, async coordination, or shared mutable state. Audit's category 5 queries this tag.
- `performance-critical` — hot path, frequently executed, or has known performance constraints
- `external-api` — makes calls to external services or third-party APIs
- `user-facing` — directly produces output the end user sees (UI components, error messages shown to users)
- `internal-only` — explicitly not for external consumption (helpers, private utilities)
- `experimental` — feature-flagged, in development, not for production reliance
- `deprecated` — marked for removal; do not extend
- `boundary` — at the boundary of the system (entry points, exit points, public API surface)
- `pure` — no side effects; pure function of inputs
- `idempotent` — safe to retry; calling twice has same effect as once
- `transactional` — wraps a database transaction or atomic operation
- `long-running` — expected to take significant time (seconds or longer)
- `rate-limited` — has known rate limits (either imposed or self-imposed)

---

## Technical tags — *how the code works*

- `async` — async/await, futures, promises
- `streaming` — works with streams (reads/writes incrementally)
- `recursive` — uses recursion (when significant — not for trivial cases)
- `regex-heavy` — significant regex usage (worth reviewing for ReDoS)
- `unsafe` — uses unsafe blocks (Rust), eval(), or other unsafe primitives
- `singleton` — singleton pattern; global state involved
- `factory` — factory or builder pattern
- `event-driven` — event emitter, listener, or pub/sub pattern
- `generic` — heavy use of generics / type parameters
- `macro-heavy` — significant use of macros (Rust) or codegen
- `reflection` — uses runtime type inspection / reflection

---

## File-only tags — only meaningful at file level, not function level

- `entry-point` — application entry point (server.ts, main.rs, index.html)
- `test` — test file (also reflected in `test_file: true` field)
- `fixture` — test fixture or test data
- `mock` — mock or stub for testing
- `generated` — auto-generated; do not edit by hand
- `vendored` — third-party code pulled into the source tree
- `migration-file` — single database migration file
- `documentation` — documentation file (`.md`, `.mdx`, `.rst`, `.txt`). Applied to all docs.
- `documentation-class:spec` — high-information design spec, plan, roadmap, architecture doc (v0.2.1)
- `documentation-class:operational` — project conventions, contributing guide, style guide (v0.2.1)
- `documentation-class:informational` — README, CHANGELOG, user guide, misc (v0.2.1)
- `canonical-spec` — applied only to the file designated `is_canonical_spec: true` in structure.json (v0.2.1)
- `config-file` — configuration file (separate from `config` domain)

---

## Operational tags — *for operational readiness (audit category 8)* (v0.2 addition)

These tags identify files relevant to operational concerns. They help audit's category 8 (Operational Readiness) consult the codemap instead of grepping the repo. Apply at file level, sometimes function level.

- `deployment` — deployment scripts, infrastructure-as-code (Terraform, CloudFormation), launch scripts
- `dockerfile` — Dockerfiles, docker-compose configs
- `ci-config` — CI/CD pipeline definitions (`.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`)
- `health-check` — health endpoints, liveness/readiness probes, status pages
- `monitoring` — metrics emission, observability hooks, alerting setup (more specific than `metrics`)
- `backup-restore` — backup creation, restore procedures, data export
- `secret-management` — secret loading, KMS interaction, vault access (distinct from `crypto` which is about algorithms)
- `migration-runner` — migration execution logic (the code that *runs* migrations, distinct from individual migration files)
- `rate-limit-config` — rate limiting configuration, quota enforcement
- `feature-flag` — feature flag definitions or evaluation
- `pause-resume` — code that supports pausing/resuming background work (per spec)

**Why these matter for audits:** audit's category 8 asks operational questions ("is there a health check?", "are migrations forward-only?", "is there a pause/resume primitive for workers?"). With these tags, those questions become codemap queries instead of grep searches. Category 8 stops being the "underaudited" category.

---

## Picking tags — guidelines

**Use the minimum set that's informative.** A typical source file has 2–4 tags. More than 6 is usually a sign of either over-tagging or that the file does too many things.

**Domain first, then concern, then technical.** When listing tags in a file's entry, sort domain tags first (`auth`), then concerns (`security-sensitive`), then technical (`async`). This makes the JSON more scannable.

**File tags vs. function tags.** A file's tags are the union of what's true about it as a whole. A specific function's tags can be a *subset* (it's the only `security-sensitive` function in an otherwise-routine file) or include *additional* tags the file as a whole doesn't warrant.

**When in doubt, leave it out.** A wrong tag is worse than no tag — it sends consumers to the wrong files. Empty tags arrays are fine.

**Spec refs are not tags.** Spec references go in the `spec_refs` field, not in `tags`. Tags are for properties intrinsic to the code; spec refs are for "what design promise does this implement."

---

## Adding new tags

If a project legitimately needs a new tag (e.g., a domain not covered here), add it during a Cartographer run with a brief justification in the run summary:

> "Added new domain tag `pdf-generation` — 4 files in this codebase produce PDFs and the existing vocabulary didn't cover it."

If multiple projects start needing the same new tag, promote it into this reference file in a future Cartographer version.

Do **not** invent variant spellings (`security`, `sec`, `securitysensitive`) — they fragment the vocabulary. Stick to existing tags when their meaning fits, and add only when there's a genuine gap.
