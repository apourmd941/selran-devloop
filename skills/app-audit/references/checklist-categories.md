# Standard Audit Checklist Categories

When generating `AUDIT_CHECKLIST.md` from a design spec (Phase 1.3 of the audit skill), use these ten categories as the default scaffold. Add or remove categories based on the spec, but cover at least these areas for any nontrivial app.

**Static vs runtime:** these checklist items are mostly *static* — verified by reading code and the spec. They cannot prove runtime behavior. The runtime layer is the smoke/integration harness run by pre-commit-verification, whose per-category failures app-audit folds into the findings (Phase 0.3). A few items below are explicitly the static half of a runtime concern (e.g., "CORS middleware is registered" is static; "CORS header is correct under a real request" is harness [1+4]). Both halves are needed — presence ≠ correct behavior. See "Runtime harness mapping" at the end.

For each category below: a short description, why it matters, representative checklist items, and the kinds of findings to look for. Use these as a starting set; specialize from the actual spec.

---

## Category 1 — Schema Integrity

**Why it matters:** schema mistakes cause data loss and bugs that surface late and are hard to roll back.

**Representative items:**
- Every foreign key column has an index
- Nullable columns: every NULL is intentional and the code handles it
- Non-nullable columns: every INSERT path provides a value
- Status/enum columns: every transition is reachable; no orphan states
- Uniqueness constraints match the spec
- Composite indexes match the actual query patterns
- Migration order is consistent (no migration depends on a later one)
- No "soft delete" columns that the queries forget to filter on
- JSONB columns have documented shape or a `schema_version` key
- `CHECK` constraints exist where the spec implies bounded values

**Common findings:** missing index on FK, status enum the code can produce but the DB constraint doesn't allow, JSONB used where a column would be safer.

---

## Category 2 — Data Flow Correctness

**Why it matters:** subtle correctness bugs in state machines and pipelines are the bugs users notice last but suffer from most.

**Representative items:**
- Every state value has a worker/handler that moves it forward
- Every "in-progress" status has a timeout or recovery path
- Failure paths set status correctly (not silently retried forever)
- Multi-step state changes are transactional
- Workers idempotent — re-running a worker on the same row doesn't corrupt it
- Backfill paths match the spec's tier/window definitions
- No code reads a state value before the worker that produces it has run
- Reactive UI updates fire on every relevant state change, not just some

**Common findings:** "pending" status with no worker, error path that leaves status='processing' forever, race between two workers producing inconsistent state.

---

## Category 3 — Security

**Why it matters:** a single security finding can be product-ending. Highest stakes.

**Representative items:**
- Credentials (OAuth tokens, API keys, passwords) never logged
- Credentials never appear in error messages or stack traces sent to telemetry
- Credentials live in a vault/keychain, not in DB
- PII never in URL parameters, query strings, or referrer headers
- No user input flows into SQL without parameterization
- No user input flows into shell commands or file paths without sanitization
- File uploads validate type, size, and don't allow path traversal
- Any "forget" / "delete me" feature actually cascades through embeddings, derivations, backups
- HTTPS/TLS enforced for all external traffic
- Local app: file permissions on sensitive files (DB, keychain) are user-only
- **Cross-origin webview (desktop apps): the required CORS/middleware layer is registered for the webview origin.** This is the static presence half of harness category [1+4] — verify the layer exists and names the right origin; the harness verifies the header is actually correct at runtime. (This is failure-taxonomy category #6: "missing layers — required middleware for cross-origin webview.")

**Common findings:** token written to a log file on retry; password reset link emailed without TLS-only flag; `os.system` with user input; webview makes cross-origin calls to the local backend but no CORS layer is registered, so it works in the dev browser and fails in the bundled app.

---

## Category 4 — Error Handling and Recovery

**Why it matters:** errors are inevitable; the question is whether they degrade gracefully or compound.

**Representative items:**
- Every async call has a defined failure path
- Worker crashes don't lose in-progress state
- Network failures retry with backoff and a max-retry cap
- Errors that should bubble up actually bubble up (not silently swallowed)
- Errors that should be retried locally aren't bubbled to the user
- Database connection failures reconnect cleanly
- LISTEN/NOTIFY (or other event subscribers) reconnect on disconnect
- Out-of-disk, out-of-memory paths are tested or at least gracefully fail
- User-facing error messages don't expose internals

**Common findings:** `.catch(() => {})` swallowing real errors; infinite retry loop with no cap; worker that exits silently on unhandled exception.

---

## Category 5 — Concurrency and Race Conditions

**Why it matters:** races are bugs that don't show in dev and ruin production. Hard to find, easy to miss.

**Representative items:**
- Multi-worker access to shared rows uses appropriate locking
- Optimistic concurrency: version columns checked on update
- Read-modify-write paths are transactional or use compare-and-swap
- File operations on shared paths are mutually exclusive when needed
- LISTEN/NOTIFY subscribers handle out-of-order events
- Worker pool size doesn't exceed connection pool size
- No "check then act" patterns without locking
- UI doesn't render partial state from mid-transaction reads

**Common findings:** two workers can both flip a status from "pending" to "processing"; UI badge count and tab count diverge under load; reactive subscriber misses events during reconnect.

---

## Category 6 — Resource Bounds and Performance

**Why it matters:** apps that work on small data fail on large data. Local-first apps especially.

**Representative items:**
- Every list query has pagination or a hard limit
- Every table that grows has a documented retention or compaction story
- Embedding/vector indexes won't blow past memory at expected scale
- Background workers throttle themselves on a metered connection
- Indexes match the actual query patterns (not just FK indexes)
- N+1 query patterns are absent or intentional
- Bulk operations batched, not row-by-row
- Caches have bounded size and eviction
- Files (logs, backups, exports) rotated or capped

**Common findings:** unbounded `derivations` table; query that loads all messages into memory; vector index that uses a million-row IVFFlat with no probing tuning.

---

## Category 7 — User-Facing Promises (Spec Compliance)

**Why it matters:** every "never" and "always" in the spec is a promise. Breaking promises destroys trust faster than bugs.

**Representative items (extract from spec):**
- Every `must`, `must not`, `never`, `always` in the spec is checked
- Every numeric bound (thresholds, windows, caps) matches code
- Every named invariant ("X attaches to Y, never Z") is verified
- Every architectural decision (one DB, no auto-send, local-first) is honored
- Every UX promise ("nothing deleted without confirmation") is enforceable
- Every privacy claim ("data never leaves the device") is true in all code paths

**This is the category pre-commit hooks cannot help with.** Lint and typecheck have no opinion about whether the code matches the spec. This is where audits earn their keep.

**Common findings:** the spec says "never auto-send" but a "send-after-delay" experiment is hiding in a worker; the spec says "12 months only" but the vectorizer has no age filter; the spec says "two tables for commitments" but the code uses one polymorphic table.

---

## Category 8 — Operational Readiness

**Why it matters:** the audit isn't complete if the app can't be operated.

**Representative items:**
- Migrations run automatically and are forward-only
- Backups are possible without app-internal access
- Logs are written, rotated, and don't contain PII or secrets
- Health checks exist for the major workers
- Metrics or counters exist for the pipelines (download/categorize/vectorize progress)
- Pause/resume works for every long-running worker
- Recovery from corrupt state is documented or possible
- Version stamps in DB and code, so a future audit knows what state things are in

**Common findings:** migrations have no rollback test; no health endpoint for the worker pool; logs include OAuth tokens during error paths.

---

## Category 9 — Test Coverage

**Why it matters:** code without tests is code whose behavior is unverified. The audit's other categories find bugs that exist; this category finds *categories of bugs that could exist undetected*. It also reveals how confident the rest of the audit's findings should be: if a critical path has no test, the absence of audit findings on it is less reassuring.

**Representative items:**

- Every file tagged `security-sensitive` has at least one corresponding test file
- Every public function exported from a tagged `auth` / `db` / `worker` file has at least one test that calls it
- No test file is empty / contains only placeholder assertions (`assert True`, `expect(1).toBe(1)`, etc.)
- No tests are marked `skip` or `xit` / `xtest` without a tracking comment (owner + date)
- Test files are deterministic — no `Math.random()`, `Date.now()`, or unbounded sleeps without seeding/mocking
- Test files don't share mutable state across cases (each test isolates its setup)
- Test fixtures and mocks live near the tests they support (not scattered across the repo)
- Integration tests cover the spec-defined critical paths (every "must" in spec §X has an integration test verifying it)
- Test failures produce useful diagnostics (no `assert(condition)` without a message; no opaque `expect(x).toEqual(y)` for complex objects without context)

**Acceptance-map completeness (the spec→test mapping):**

The deepest version of "integration tests cover the critical paths" is mechanical, not impressionistic: `.audit/acceptance-map.md` maps every **user-facing** normative statement in the spec to the test that exercises it (format and maintenance rules: `references/acceptance-mapping.md`). This category verifies the map, because "the app runs but the feature behaves wrongly" is the failure class that boot-level smoke tests structurally cannot catch.

- The acceptance map exists; if it doesn't, generating it is part of this category's work (Phase 1.3b)
- Every user-facing must/never/always in the spec appears in the map
- Every mapped test actually exists, is not skipped, and asserts the *promise* (not just "doesn't crash")
- Entries marked `n/a` carry a reason ("not user-observable", "covered by harness [3]")
- `UNMAPPED` entries are findings — severity by stakes of the promise:
  - Data-loss, security, or privacy promise unmapped: **High**
  - Other user-facing promise unmapped: **Medium**
- Map references stale tests (renamed/deleted) → **Medium** (false confidence)

**Codemap-assisted queries:**

- `query structure.json.files where tags includes 'security-sensitive' and test_file false` → find security-sensitive non-test files
- Cross-reference: for each, check whether `<basename>.test.<ext>` or `tests/<path>` exists
- `query functions.json where exported true` → all public functions; check `called_by` for test-file callers

**Common findings:** entire `auth/` directory has no tests; integration tests exist but skip `xtest` the ones that test the spec's critical claims; test files use non-deterministic timestamps causing flaky CI.

**Severity guidance:**
- Untested `security-sensitive` code: **High**
- Untested public functions in non-sensitive code: **Medium**
- Skipped tests without owner/date: **Medium**
- Non-deterministic test patterns: **Medium**
- Empty or placeholder tests: **High** (worse than no tests — produces false confidence)

This category benefits from a tighter pre-commit-verification (which already runs the test suite). Pre-commit confirms tests pass; this audit confirms tests *exist and are meaningful*.

---

## Category 10 — Diagnosability

**Why it matters:** no process drives residual errors to zero. The errors that slip past every check become either "found and fixed in minutes" or "mystery that erodes trust for weeks" — and the difference is entirely decided *before* the error happens, by whether the app can tell you what went wrong. This category is what converts "there were always remaining errors" into "errors get found fast."

**Representative items:**

- Every caught-and-handled error is logged with enough context to reproduce: operation, entity IDs, relevant state — not just the exception message
- Every *swallowed* error (intentional catch-and-continue) logs at least once per occurrence class; silent `catch {}` is a finding even when intentional (log-then-continue is the floor)
- Log levels are meaningful: errors are `error`, not `info`; routine operation isn't `error` (alert fatigue hides real failures)
- A user-reported symptom can be traced: timestamps in logs, a request/operation ID that follows a pipeline across workers, or equivalent correlation
- The running version is discoverable at runtime (version stamp in logs at startup, an about/health field, DB schema version) — "which build was this?" must be answerable
- Crash/panic paths produce a persisted artifact (log line, crash file, OS crash-reporter hookup) — a crash that leaves no trace is unfixable
- Logs survive long enough to be useful: rotation exists, but rotation doesn't destroy the only evidence within hours
- State needed to reproduce data bugs is inspectable: DB is queryable by a developer, or a diagnostic export exists
- Background-worker failures are *visible* somewhere a human looks (status field, badge, health endpoint), not only in a log nobody reads
- No PII/secrets in logs (overlaps Category 3 — here the lens is "diagnostics that are safe to actually share when asking for help")

**Codemap-assisted queries:**
- `query structure.json.files where tags includes 'worker'` → check each for failure-visibility
- grep catch/except/`.catch(` sites → classify: rethrow / log-and-continue / silent

**Common findings:** worker catches all exceptions and continues with no log (failures invisible for weeks); error logs contain the exception but not which account/message it occurred for; no version stamp anywhere, so a bug report can't be tied to a build; panic in the sync loop kills the thread silently and the UI just stops updating.

**Severity guidance:**
- Silent failure path on a data-affecting pipeline: **High**
- Error logged without identifying context (can't reproduce from the log): **Medium**
- No runtime version discoverability: **Medium**
- Routine ops logged at error level (alert fatigue): **Low**

The spec's §Operational-requirements section (spec-bootstrap template §9) is this category's source when one exists; in its absence, the items above are the floor.

---

## Runtime harness mapping

The smoke/integration harness (run by pre-commit-verification) catches runtime/launch failures that static checklist items cannot. When the harness reports a failure, app-audit converts it into a finding in the mapped category (Phase 0.3). The mapping:

| Harness category | Maps to checklist category | Static counterpart item (if any) |
|---|---|---|
| [1+4] HTTP health / CORS / boot | 3 Security, 8 Operational | "CORS middleware registered" (Cat 3) |
| [2] dev vs prod-bundled context | 8 Operational | — (purely runtime) |
| [3] migration idempotency | 1 Schema integrity | "migrations forward-only / re-runnable" (Cat 1/8) |
| [5] webview behavior | 7 Spec compliance, UX | — (purely runtime) |
| [6] cross-origin middleware present | 3 Security | this IS the static item (no runtime test of its own) |
| [7] launch-env probe | 8 Operational | — (purely runtime) |
| [8] provider contract | (External integrations) | "external API error paths handled" (Cat 4) |
| [9] onboarding click-through | 7 Spec compliance, UX | — (purely runtime) |

Category #6 is the one that is *only* static — there's no runtime harness test for "is the middleware registered," because category [1+4] already tests the behavior. The checklist item in Category 3 above is its home.

If a runnable app has **no harness scaffolded at all**, that's a Category 8 finding in its own right: the entire runtime layer is unverified.

## Specializing for the spec

When generating the checklist from a specific spec, walk through the spec section by section. For each section:

1. **Pull out every imperative.** "Must," "must not," "always," "never," "only," "default to," "requires" → checklist items.
2. **Pull out every numeric bound.** Time windows, confidence thresholds, retention periods, size caps → checklist items.
3. **Pull out every architectural decision.** Each one becomes a category-7 item.
4. **Pull out every schema constraint.** FKs, uniqueness, NOT NULL → category-1 items.
5. **Pull out every concurrency claim.** "Reactive sync," "parallel workers," "transactional" → category-5 items.
6. **Pull out every critical path claim.** Every "must" gets a category-9 item: "an integration test exists verifying this."

A good checklist for a substantial spec has 60–200 items. Below 50 is probably underspecified; above 250 is probably padding.

## Updating the checklist over time

The checklist is a living document. Update it when:
- The spec changes (regenerate the relevant sections)
- A new finding type emerges that wasn't in the checklist (add an item so it gets caught next time)
- A category is consistently empty across audits (consider whether the items are right)
- The codebase grows into new territory (new language, new subsystem)

Don't let the checklist rot. A stale checklist is worse than no checklist because it produces false confidence.
