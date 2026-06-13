# SPEC.md Template (bootstrapped spec)

The structure Phase 4 writes. Sections may be added or dropped to fit the app, but keep the §-numbering scheme, the provenance markers, and the two closing sections (Open questions, Known deviations) — those are load-bearing for the audit machinery.

---

## Header block

```markdown
# <App Name> — Design Specification

**Version:** v1 (bootstrapped 2026-06-09)
**Status:** SIGNED OFF by <user> on 2026-06-09   ← or: DRAFT — UNCONFIRMED (no interview)
**Provenance legend:** [confirmed] user-affirmed intent · [observed] consistent code behavior,
not yet user-affirmed · [assumed] inferred, unverified — violations are questions, not findings.
```

The version stamp anchors app-audit's spec-drift detection (Phase 0.5.3). Bump to v2 on the first substantive post-bootstrap revision.

## Section skeleton

```markdown
## 1. Overview
What the app is, who it's for, the one-paragraph job description. No normative
statements here — context only.

## 2. Architectural decisions
The load-bearing choices, one per subsection. These are the "Postgres only",
"local-first", "no auto-send" class of statements — the ones whose silent
violation is an architecture drift finding.
### 2.1 <decision> [confirmed]

## 3. Surfaces
One subsection per user-facing surface (page, route group, CLI command,
worker with user-visible effects). For each: what it does, and its musts.
### 3.1 <surface>
- Must <...> [confirmed]
- Never <...> [observed]

## 4. Data model
Tables/collections, key relationships, status enums and their legal
transitions, uniqueness and integrity constraints the code must honor.

## 5. External integrations
Per provider: what's called, what's promised about failures, contract
assumptions worth pinning (these feed harness category [8]).

## 6. Background work
Workers, schedules, idempotency and recovery requirements.

## 7. UX promises
The user-visible "never lose my draft", "always confirm before delete",
"undo is available for N minutes" class. Each one is enforceable and
checkable — vague aspirations don't go here.

## 8. Security & privacy
Where credentials live, what is never logged, what never leaves the device,
authn/authz rules per surface. The highest-stakes section — push hardest in
the interview to get these to [confirmed].

## 9. Operational requirements
Migrations, backups, recovery, version stamping, observability requirements
(see app-audit's diagnosability category — this section is its source).

## 10. Bounds & scale
Numeric limits with their reasons: retention windows, pagination sizes,
confidence thresholds, cache caps. A bare constant from the code stays
[observed] with a "value found in code; rationale unknown" note until the
user explains or adopts it.

## 11. Open questions
Everything still [assumed], plus the user's explicit "I don't know yet"
answers. Each entry: the question, why it matters, what's at stake.

## 12. Known deviations
Statements the user confirmed where the code currently does NOT comply.
Format per entry:
- §8.2 says tokens never logged [confirmed]; `auth/refresh.rs:88` logs the
  full token on retry failure. (User: "definitely a bug.") → pre-seeded
  finding for the next audit round.
```

## Normative-statement style

- One requirement per bullet. Compound statements can't get individual verdicts.
- Use must / must not / never / always / only — the words app-audit's checklist generator extracts.
- Every normative bullet ends with its provenance marker.
- Numeric bounds inline with the statement ("retention is 12 months"), not in prose nearby.
- Explicit non-requirements are statements too: "§3.4: concurrent multi-device editing is **unspecified by choice** [confirmed]" — this stops future audits from re-asking.

## What NOT to write

- Implementation details ("uses tokio channels") unless they're decisions (§2).
- Aspirations nobody will check ("the UI should feel fast") — convert to a checkable bound or leave out.
- Restated code. The spec says what must be true; the code says how.
- Unmarked statements. An unmarked must is a bug in the spec.
