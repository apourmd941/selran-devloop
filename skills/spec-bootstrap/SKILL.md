---
name: spec-bootstrap
version: 0.2.0
description: Reconstruct a design spec (SPEC.md) for a codebase that doesn't have one — derive observed behavior from the code, interview the user to separate intent from accident, and produce a section-numbered, provenance-marked spec that app-audit can generate its checklist from. Use when the user asks to write or create a design spec, document what the app should do, or formalize requirements for an existing app — and automatically when app-audit Phase 1 finds no spec. Every statement is marked [confirmed] / [observed] / [assumed] so audits know how much to trust each claim. Optional formal surface: EARS-form requirements and Gherkin scenarios (which seed the acceptance map), architectural decisions captured as ADRs, and a C4-style context/container diagram generated from cartographer's codemap.
---

# Spec Bootstrap

Reconstruct a design spec for a codebase that never had one (or whose spec is long dead).

## Why this exists

The audit system's strongest machinery — checklist generation, spec-compliance category, spec_refs — assumes a design spec exists. Most AI-built apps don't have one. Without a spec, "does the code match the intent?" is unanswerable, and the residual-error problem ("we kept fixing things and errors kept remaining") is partly *unspecified intent*: nobody ever wrote down what the app must and must never do, so no audit could check it.

A bootstrapped spec is **reconstructed intent**, not original intent. The code shows what the app *does*; only the user knows what it *should* do. The gap between those two is exactly where the bugs live — which is why the interview (Phase 3) is the heart of this skill, not the code reading.

## When to use this skill

- User asks to "write a design spec," "document what this app should do," "formalize the requirements," "create a SPEC.md"
- app-audit Phase 1 finds no design spec and needs one for checklist generation
- An existing spec is so stale the user wants to start over from current reality

Do NOT use when a current spec exists and just needs updating — that's an ordinary edit, not a bootstrap.

## The provenance system (core idea)

Every normative statement in a bootstrapped spec carries a provenance marker:

| Marker | Meaning | How audits treat violations |
|---|---|---|
| `[confirmed]` | The user explicitly affirmed this is intended behavior | Normal finding at normal severity |
| `[observed]` | The code does this consistently; user hasn't been asked | Normal finding, with a note that the baseline is observed not confirmed |
| `[assumed]` | Inferred from convention or partial evidence; plausible but unverified | Not a finding — a **question** (app-audit Phase 3.6: ask, don't flag) |

The markers are the honesty layer. A spec where everything silently looks authoritative would launder guesses into requirements — violations of guessed requirements are noise, and noise erodes trust in the audit. The goal of the interview is to move as many statements as possible to `[confirmed]`.

## Workflow — five phases

### Phase 0 — Confirm the bootstrap is needed

1. Look for an existing spec (same patterns app-audit uses: `*DESIGN*.md`, `*SPEC*.md`, `ARCHITECTURE.md`, `.codemap/spec-config.yml` `canonical_spec`).
2. If one exists and is plausibly current: stop, tell the user, offer a refresh instead.
3. If one exists but is dead (describes a different app, predates a rewrite): confirm with the user before superseding it. Never silently replace a spec.

### Phase 1 — Inventory the app

Build the factual skeleton from the code. Use cartographer's codemap if present (build it if not — this is a legitimate auto-trigger); fall back to direct exploration otherwise.

Catalog:
- **Surfaces**: UI pages/views, API routes, CLI commands, background workers
- **Data model**: tables/collections, key relationships, enums and status fields
- **External integrations**: APIs called, auth providers, webhooks
- **Lifecycle**: how it starts, migrates, recovers, shuts down
- **Existing promises in the small**: validation rules, confirmation dialogs, permission checks — code that *implies* a requirement

This phase is mechanical. No normative claims yet.

### Phase 2 — Derive observed behavior

For each inventory item, write candidate normative statements in spec language — and mark every one `[observed]` or `[assumed]`:

- A `DELETE` route that requires a confirmation token → "Destructive actions require explicit confirmation `[observed]`"
- Messages always written inside a transaction with their attachments → "Message + attachment writes are atomic `[observed]`"
- A 0.75 threshold constant in the categorizer → "Categorization requires confidence ≥ 0.75 `[observed]` — *value found in code; intent unknown*"
- No rate limiting anywhere → candidate statement for the interview: is that a decision or an omission?

Two derivation rules:
1. **Code is evidence of behavior, never evidence of intent.** "The code does X" never becomes "the app must X" without a marker.
2. **Absences are candidate requirements too.** Missing auth on a route, missing pagination, missing encryption — each becomes an interview question, because "the spec is silent" is how those bugs survived every previous review.

### Phase 3 — Interview the user (the heart)

Convert `[observed]`/`[assumed]` into `[confirmed]`, and capture intent that is **not** in the code at all. Full question design and batching rules: `references/interview-protocol.md`. The essentials:

- **Batch questions** (one round of 6–10, at most three rounds). Don't drip-feed.
- **Highest stakes first**: data loss, security, privacy, money. A typo in a label can stay `[assumed]` forever; "should deleting an account cascade to backups?" cannot.
- **Ask about accidents explicitly**: "The code does X — intended, or accident?" Answers of "accident" are *immediate findings* — log them for app-audit; don't write them into the spec as requirements.
- **Ask about the missing**: "The app has no offline story / no rate limiting / no export. Decision or gap?" Gaps become spec requirements the code doesn't yet meet — exactly what the next audit should flag.
- Every answer updates a statement's marker, severity-relevant wording, or spawns a finding. No answer is just filed away.

**Outcome classes from each answer:**
- "Yes, intended" → `[confirmed]`
- "No, that's a bug" → finding for the audit log; spec records the *correct* behavior `[confirmed]`
- "I don't care / either way" → record as explicit non-requirement ("§N.M: unspecified by choice") so future audits don't ask again
- "I don't know yet" → stays `[assumed]`, listed in the spec's open-questions section

### Phase 4 — Write SPEC.md

Use the structure in `references/spec-template.md`. Non-negotiables:

- **§-numbered sections** (`## 3. Surfaces`, `### 3.2 Calendar`) so cartographer's spec_refs and app-audit's checklist machinery work against it.
- **Version stamp**: `v1 (bootstrapped YYYY-MM-DD)` in the header, so spec-drift detection has an anchor.
- **Provenance marker on every normative statement.** No exceptions.
- **An "Open questions" section** holding everything still `[assumed]` plus the user's "I don't know yet" answers.
- **A "Known deviations" section**: statements the user confirmed where the code currently *doesn't* comply — these are pre-seeded findings for the next audit round, with the user's words as evidence.

**Optional formalization (offer once, don't impose).** Prose requirements are
ambiguous in predictable ways ("the app should handle errors" — which errors,
doing what?). Two formal surfaces fix specific ambiguity classes — formats and
worked examples in `references/formal-spec.md`:

- **EARS form** for testability-critical statements: rewrite the statement as
  `WHEN <trigger> [WHERE <state>] THE SYSTEM SHALL <response>` next to the
  prose (the prose stays primary; EARS is the precision layer). Apply it where
  ambiguity is expensive — data loss, security, money, concurrency — not to
  every sentence; a fully-EARS spec is unreadable.
- **Gherkin scenarios** for user-facing musts: each `Given/When/Then` scenario
  goes in the spec section it formalizes, carries the section number, and
  **seeds the acceptance map** (app-audit Step 1.3b) — a scenario is a test
  specification, so an UNMAPPED row already says exactly what the missing test
  must assert. Provenance markers carry over: a scenario derived from an
  `[assumed]` statement is itself assumed, and stays out of the acceptance map
  until confirmed.

### Phase 5 — Sign-off and handoff

1. Present the spec; user reads and approves (or edits — their edits are `[confirmed]` by definition).
2. Write `.codemap/spec-config.yml` naming the new spec as `canonical_spec`.
3. Refresh cartographer so doc classification and spec_refs pick it up.
4. **Offer the architecture record** (skip silently if declined):
   - **ADRs** — the interview surfaces architectural decisions ("Postgres only",
     "no auto-send", "sync is pull-based because…"). Decisions with a *why*
     deserve their own record: offer to write each as an ADR in `docs/adr/`
     (`NNNN-<slug>.md`, Context / Decision / Consequences — template in
     `references/formal-spec.md` §3). The spec states *what must hold*; the ADR
     preserves *why it was chosen*, which is what the next person needs before
     un-choosing it. Cross-link: spec section cites the ADR, ADR cites the
     section.
   - **C4-style diagram** — generate a context/container diagram as Mermaid
     from cartographer's codemap (structure + dependencies + external
     integrations from Phase 1), embedded in the spec or `docs/architecture.md`.
     Recipe: `references/formal-spec.md` §4. Mark it `[observed]` — it
     describes the code as mapped, and regenerates on request rather than
     rotting.
5. Hand off: "Spec bootstrapped and signed off. app-audit can now generate its checklist from it (Phase 1.3). N statements confirmed, M observed, K assumed; J known deviations pre-seeded as findings."

Don't auto-invoke app-audit; the user decides when to audit.

## Non-interactive mode (driver / headless invocation)

The interview is the heart of this skill, and there is no user to interview. Headless behavior:

- Run Phases 0–2 and 4: produce the draft with everything marked `[observed]`/`[assumed]` and the header stamped **`DRAFT — UNCONFIRMED (no interview)`**.
- Do NOT write `spec-config.yml` pointing at it as canonical — an unconfirmed draft must not silently become the source of truth. Instead note it for the user.
- app-audit may proceed against the draft with the provenance rules above: `[observed]` violations are findings-with-caveat, `[assumed]` violations are questions queued for the user.
- The first interactive session should run Phase 3 to upgrade the draft.

## Hard rules

1. **Never write an unmarked normative statement.** Every must/never/always carries `[confirmed]`, `[observed]`, or `[assumed]`.
2. **Never let observed behavior masquerade as intent.** "The code does X" is the start of a question, not the end of one.
3. **Never silently replace an existing spec.** Phase 0 confirms first.
4. **Accidents go to the audit log, not the spec.** When the user says "that's a bug," the spec records the correct behavior and the bug becomes a finding.
5. **The user owns the spec.** This skill drafts; the user confirms. An unconfirmed draft is never `canonical_spec`.

## How this skill relates to the others

| Skill | Relationship |
|---|---|
| **cartographer** | Provides the inventory (Phase 1) and consumes the result (spec_refs, doc classification after Phase 5) |
| **app-audit** | Invokes this skill from Phase 1 when no spec exists; generates its checklist from the bootstrapped spec; respects provenance markers when grading spec-compliance findings |
| **audit-fix** | Indirect — fixes the "known deviations" findings this skill pre-seeds |

## Standalone invocation phrases

- "Write a design spec for this app"
- "Document what this app should do"
- "Bootstrap a spec" / "Run spec-bootstrap"
- "Formalize the requirements"
- "We never wrote a spec — create one from the code"

## Reference files

- `references/spec-template.md` — the SPEC.md structure: section layout, normative-statement style, provenance markers, versioning, open-questions and known-deviations sections. Read in Phase 4.
- `references/interview-protocol.md` — question design, batching, stakes-ordering, and the answer→outcome mapping. Read before Phase 3.
- `references/formal-spec.md` — EARS patterns with worked rewrites, Gherkin scenario style + acceptance-map seeding, the ADR template, and the C4-from-codemap Mermaid recipe. Read for Phase 4's formalization offer and Phase 5 step 4.
