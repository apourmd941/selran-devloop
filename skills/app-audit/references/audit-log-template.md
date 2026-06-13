# Templates: AUDIT_CHECKLIST.md and AUDIT_LOG.md

Copy these templates verbatim when creating the files for the first time (Phase 1 of the audit skill). Adjust category content based on the project's design spec.

---

## Template: AUDIT_CHECKLIST.md

```markdown
# Audit Checklist

**Project:** [project name]
**Spec source:** [path to design spec / SPEC.md / etc.]
**Last regenerated from spec:** YYYY-MM-DD
**Checklist version:** 1

This document defines what gets verified during an audit. Every item is a yes/no check with a clear verdict. Audits work through every item in every scoped category — no skipping.

When the spec is updated, regenerate this checklist. Stale checklists produce false confidence.

---

## How to use this checklist

- Each category is a scoped audit unit. An audit round picks one or more categories.
- Within a category, every item gets one of four verdicts: Verified clean, Finding, Cannot verify, or Out of scope.
- Items reference the spec section where applicable: `(spec §3.2)`.
- Severity is assigned at finding time, not in this checklist.

---

## Category 1 — Schema Integrity

- [ ] 1.1 Every foreign key column has an index
- [ ] 1.2 No nullable column where the spec implies a required value
- [ ] 1.3 Every status/enum column's allowed values match the code
- [ ] 1.4 [add items derived from spec section on schema]
- [ ] 1.5 ...

## Category 2 — Data Flow Correctness

- [ ] 2.1 Every "pending" status in `message_pipeline_state` has a worker
- [ ] 2.2 Worker crash on row X leaves X recoverable (no permanent "processing" lock)
- [ ] 2.3 [add items from spec section on pipelines]

## Category 3 — Security

- [ ] 3.1 OAuth tokens never in Postgres (spec §8.1) — confirmed via grep for token-related columns
- [ ] 3.2 OAuth tokens never in logs — confirmed via log-write call audit
- [ ] 3.3 Forget primitive (spec §8.3) cascades through embeddings, derivations, message bodies
- [ ] 3.4 ...

## Category 4 — Error Handling

- [ ] 4.1 Every async worker has a top-level error handler that updates state
- [ ] 4.2 LISTEN/NOTIFY subscriber reconnects with backoff on disconnect (spec §14.5)
- [ ] 4.3 ...

## Category 5 — Concurrency

- [ ] 5.1 Multi-worker access to `message_pipeline_state` rows uses row-level locking or status compare-and-swap
- [ ] 5.2 `attention_summary` updates are reactive and consistent across UI views (spec §4.4)
- [ ] 5.3 ...

## Category 6 — Resource Bounds

- [ ] 6.1 `message_embeddings` warm/cold policy (spec §6.1) is enforced; no warm rows past TTL
- [ ] 6.2 `derivations` table has a compaction job; isn't unbounded
- [ ] 6.3 Vectorization respects 12-month window (spec §1.4)
- [ ] 6.4 ...

## Category 7 — Spec Compliance (User-Facing Promises)

- [ ] 7.1 No auto-send path exists (spec §7.3, §0 non-goals)
- [ ] 7.2 No auto-delete path in classification (spec §2.4)
- [ ] 7.3 Max auto-action on quarantine is archive, never delete (spec §2.4)
- [ ] 7.4 Confidence threshold 0.75 enforced for surfacing (spec §3.5)
- [ ] 7.5 Messages attach to `account_contacts`, never directly to `persons` (spec §3.2)
- [ ] 7.6 ...

## Category 8 — Operational Readiness

- [ ] 8.1 Migrations are forward-only and run at app startup (spec §14.2)
- [ ] 8.2 Pause/resume works for every background worker (spec §9.3)
- [ ] 8.3 Indexing progress UI reflects real state, not cached estimates (spec §2.2)
- [ ] 8.4 ...

---

## Cross-cutting checks (run once per audit)

- [ ] X.1 No TODO/FIXME/XXX without owner and date
- [ ] X.2 No commented-out code blocks > 3 lines
- [ ] X.3 No print/console.log/dbg! in non-test code
- [ ] X.4 All prod dependencies pinned to specific versions
- [ ] X.5 No secrets in source (spot-check; pre-commit gitleaks handles primary scan)
```

---

## Template: AUDIT_LOG.md

```markdown
# Audit Log

Durable history of audit rounds for this project. Each round appends an entry. Read this before starting a new audit so you don't re-find fixed issues or skip already-covered ground.

Findings have statuses:
- `open` — not yet addressed
- `fixed` — confirmed resolved (cite commit if possible)
- `deferred` — accepted as known, scheduled for later (state why)
- `dismissed` — examined and determined not to be a real issue (state why)
- `superseded` — replaced by a different finding or no longer applicable

---

## Round 1 — YYYY-MM-DD

**Pre-commit baseline at audit start:**
- Tests: 412 passed, 0 failed
- Lint: clean
- Typecheck: clean
- Build: success
- Smoke: backend boot OK, /health responds, frontend build OK
- Git: clean working tree
- Commit at audit start: `abc123def`

**Codemap state at audit start:**
- State: refreshed incrementally
- Files mapped: 247
- Last refresh commit: `abc123def`
- Warnings: 6 total (1 high, 3 medium, 2 low)
- High-severity warnings carried forward: src/auth/refresh.ts and src/auth/refresh_v2.ts are ~87% identical (near-duplicate)

**Scope:** Categories 1, 3, 5
**Checklist version at time of audit:** 1
**Auditor:** [name or "Claude via app-audit skill"]
**Skill versions:** app-audit 0.2.1, cartographer 0.2.1 (codemap consulted)
**Pre-commit coverage skipped:** lint, format, typecheck, gitleaks, test-suite (all clean at baseline)

### Findings

#### [CRITICAL] OAuth refresh token written to log on retry failure
- **Category:** 3 — Security
- **Location:** `src/auth/refresh.ts:88`
- **Type:** safety
- **Description:** When the refresh call fails, the error is logged via `logger.error(err)` and `err` contains the full request body including the refresh token. Logs are written to `~/Library/Logs/...` which is captured in Time Machine backups and may be sent to telemetry.
- **Evidence:** [code snippet]
- **Suggested fix:** Redact request bodies in error logging; or strip tokens from errors before throwing.
- **Effort:** small
- **Status:** open
- **Resolution notes:** _(filled in when fixed)_

#### [HIGH] Two workers can both transition `pending` → `processing`
- **Category:** 5 — Concurrency
- **Location:** `src/workers/categorize.rs:142`
- **Type:** concurrency
- **Description:** Worker reads status, checks if pending, updates to processing — without a row lock. Under concurrent execution two workers can both pass the check and both call update; second update is a no-op but both then run the work, producing duplicate derivations.
- **Evidence:** [code snippet + reasoning]
- **Suggested fix:** Use `UPDATE ... WHERE status = 'pending' RETURNING id` and check rows-affected; or `SELECT ... FOR UPDATE SKIP LOCKED`.
- **Effort:** small
- **Status:** open

[... more findings ...]

### Coverage declaration

- **Scope:** Categories 1, 3, 5
- **Checklist items covered:** 27 of 27 in scoped categories
- **Items I could not verify (and why):**
  - 3.4.2 — needs runtime trace; static check inconclusive
  - 5.6.1 — would need fault injection
- **Confidence:**
  - Critical in scope: HIGH none remain
  - High in scope: HIGH none remain
  - Medium in scope: MODERATE
- **Out of scope:** Categories 2, 4, 6, 7, 8 — no claims made
- **Recommended next round:** Categories 7 and 2

### Auditor notes for next round

- The worker pool pattern in `categorize.rs` is repeated in `vectorize.rs` and `download.rs`; the race condition likely exists in all three. Worth a focused concurrency pass after the first fix lands.
- `derivations` table is at 1.2M rows in dev; will need compaction discussion in resource-bounds audit.

---

## Round 2 — YYYY-MM-DD

[... same format ...]
```

---

## Notes on using the templates

**Don't import this whole thing verbatim into a real project's checklist.** The category items above are placeholders/examples. The actual items should be derived from the project's own design spec following the rules in `checklist-categories.md`.

**Severity at finding time, not checklist time.** A checklist item like "OAuth tokens never in logs" doesn't have a severity until you find a violation. The violation's severity depends on context (is it a hot path? does it actually get sent somewhere? etc.).

**Keep the log truthful.** Don't mark things `fixed` you haven't verified are fixed. Don't mark things `dismissed` without a real reason recorded. The audit log is institutional memory; it has to be accurate to be useful.

**Append, don't rewrite.** When updating finding statuses, edit in place. When starting a new round, append a new section. Never delete old rounds — they're the trail.
