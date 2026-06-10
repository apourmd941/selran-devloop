---
name: app-audit
version: 0.7.0
description: Run a rigorous, repeatable, convergent audit of a codebase covering schema integrity, data flow, security, concurrency, resource bounds, spec compliance, operational readiness, test coverage with spec→acceptance-test mapping, and diagnosability. Use whenever the user asks to audit, review, QA, verify, or validate a codebase — especially before a release or after a major refactor. Consumes cartographer's codemap for targeted retrieval; produces a persistent AUDIT_LOG.md so audits converge across rounds. Pre-commit-verification first for a clean baseline; invokes spec-bootstrap when no design spec exists; hands off to audit-fix at the end.
---

# App Audit

A repeatable, convergent audit method for software projects of any size or language.

This skill exists because ad-hoc audits drift. Each round picks a different lens and finds different things; the user fixes them, asks for another audit, and another batch surfaces — not because new issues appeared, but because the previous round focused elsewhere. This skill replaces drifting audits with **mechanical, checklist-driven, scoped audits that converge quickly toward a stable codebase.**

## When to use this skill

- User says "audit," "review," "check the code," "QA," "verify," or asks for a "deep look"
- User has asked for multiple audits in succession and wants them to stop finding new things
- Preparing for a release, lock-down, or version cut
- After any significant refactor or feature drop
- When the user is back at the codebase after a long break and wants to know its state

Trigger this even when the user phrases it casually. Default to using this skill rather than improvising an audit.

## Core principles

1. **Audits are scoped by checklist, not by judgment.** Without a checklist, "deep" means whatever feels deep that moment. The checklist is the contract: every item gets verified, every item gets a verdict.
2. **Findings are durable across audit rounds.** Use `AUDIT_LOG.md` so the next audit doesn't re-find fixed issues or skip categories already covered.
3. **Severity is declared, not implied.** Every finding gets Critical / High / Medium / Low / Info — defined precisely so the user can prioritize.
4. **Coverage is declared at the end.** Don't imply completeness. Say what was checked, what wasn't, and the confidence per category.
5. **Convergence over comprehensiveness.** Round 1 should find ~90% of findable issues in scoped categories. Rounds 2+ should hit diminishing returns fast.

## High-level workflow

A seven-phase process. Phases can be paused between sessions; state persists in the repo.

- **Phase 0 — Baseline.** Ensure pre-commit-verification has been run and the repo is in a clean mechanical state.
- **Phase 0.5 — Cartography.** Build or refresh the codemap so retrieval in Phase 3 is targeted instead of grep-based.
- **Phase 1 — Setup.** Bootstrap or read the audit infrastructure in the repo.
- **Phase 2 — Scope.** Agree with the user on which categories to audit this round.
- **Phase 3 — Execute.** Work through each scoped category exhaustively, consulting the codemap.
- **Phase 4 — Report.** Produce the findings list with severities, file:line refs, and rationale.
- **Phase 5 — Close.** Declare coverage and confidence, update the audit log, hand off to audit-fix.

Do not skip phases. Do not interleave them.

---

## Phase 0 — Baseline (pre-commit-verification first)

**Goal:** ensure the codebase is in a clean mechanical state before auditing for architectural concerns. There is no value in auditing a repo that doesn't compile.

### Step 0.1 — Check if pre-commit-verification has been run recently

If the user has a `pre-commit-verification` skill (or equivalent), it should run before this audit. Ask:
> "Has pre-commit-verification been run on the current state? If not, I'd suggest running it before the audit — there's no point reviewing architectural concerns on code that doesn't build."

### Step 0.2 — Run it if not already run

Pre-commit-verification's output is a prerequisite for this audit:
- Tests passing
- Lint clean
- Type-check clean
- Build successful
- Smoke/integration harness passing (binary-launch, migration idempotency, provider mocks, headless webview, env probe — the runtime layer that catches launch/integration failures unit tests miss)
- Repo state acknowledged (clean or with known dirty paths)

If pre-commit fails on the mechanical checks (tests/lint/build), **stop. Fix those first.** Audit findings on top of a broken build are noise.

**Harness failures are different — they don't block the audit; they become findings.** A failing smoke/integration test (health 500, non-idempotent migration, provider contract drift, webview console errors) is a real runtime defect. Capture it as a finding in this round (see Step 0.3) rather than stopping. These are exactly the failure classes the audit exists to surface and audit-fix exists to resolve.

This is the single workflow the user runs: cartographer → app-audit → audit-fix. The user does **not** run pre-commit-verification separately. app-audit is the one place pre-commit runs, and its full results — including the per-category harness outcomes — are folded into `AUDIT_LOG.md` here so audit-fix has everything from one source.

### Step 0.3 — Capture FULL pre-commit + harness results in the audit log

Record the complete pre-commit state at start — not just pass/fail, but the per-category harness outcomes, so the runtime layer is part of the durable record:

> "Pre-commit baseline at audit start (YYYY-MM-DD):
> - Tests: 412 passed, 0 failed
> - Lint / Typecheck / Build / Format: clean
> - Smoke/integration harness:
>   - [1+4] HTTP health smoke: PASS
>   - [2] dev/prod matrix: FAIL (prod-bundled — /api/health 500)
>   - [3] migration idempotency: FAIL (2nd run errors)
>   - [5] webview e2e: PASS
>   - [7] launch-env probe: PASS
>   - [8] provider mocks: PASS
>   - [9] onboarding clickthrough: PASS
> - Git: clean working tree at commit abc123"

**Convert each harness FAILURE into a finding** in this audit round. Grade severity by impact and locate it at the root-cause file (not the test file). Tag the finding with its source so audit-fix knows it's behavioral (re-verified by re-running the check, not just re-reading code):

```
## [Critical] Migration 0003 is not idempotent

**Category:** 1 — Schema integrity
**Location:** backend-rs/migrations/0003_org_map.sql
**Type:** bug
**Source:** smoke-harness [3] migration_idempotency

**Description:** Second migration run errors — re-running migrations (which
happens on every boot) fails. Caught by the migration idempotency smoke test.

**Evidence:** Harness [3] output: `ERROR: relation "org_edges" already exists`
on the second run. The CREATE lacks IF NOT EXISTS / is not guarded.

**Suggested fix:** Make the migration idempotent (guard the CREATE, or split the
re-runnable part). Schema change — audit-fix will stop and ask before applying.

**Effort estimate:** small
```

Map harness categories to audit categories when grading:
- [1+4] health/CORS/boot → Security boundaries or Operational readiness
- [2] dev/prod context → Operational readiness
- [3] migration idempotency → Schema integrity
- [5] webview behavior → Spec compliance / UX
- [7] launch env → Operational readiness
- [8] provider contract → External integrations
- [9] onboarding → UX / spec compliance

If pre-commit-verification reports the harness isn't scaffolded yet (a runnable app with no smoke harness), record that as a **High** Operational-readiness finding: "No runtime smoke harness — launch/integration failure classes are unverified. Scaffold via pre-commit-verification." This is itself a gap the audit should surface.

### The clear dividing line

Pre-commit-verification and app-audit cover different failure modes and never duplicate work:

| Concern | Owned by |
|---|---|
| Unit / integration / end-to-end tests pass | pre-commit |
| Smoke checks pass | pre-commit |
| Lint, type-check, build, format | pre-commit |
| Secret scan, dependency scan | pre-commit |
| Repo state acknowledged | pre-commit |
| **Schema integrity vs. spec** | app-audit |
| **Pipeline state machine completeness** | app-audit |
| **Security architecture (where tokens live, what's logged)** | app-audit |
| **Error-handling design (not just "did the test pass")** | app-audit |
| **Race conditions and concurrency safety** | app-audit |
| **Resource bounds and growth patterns** | app-audit |
| **Spec compliance — every "must / never / always"** | app-audit |
| **Operational readiness (migrations, backups, pause/resume)** | app-audit |

**The shorthand:** pre-commit asks "does it work?" Audit asks "does it match the spec, and will it keep working at scale?"

---

## Phase 0.5 — Cartography

**Goal:** make sure the codemap is fresh enough to consult during Phase 3. The codemap lets retrieval be targeted (graph lookup) instead of exhaustive (grep). This is what makes round-2+ audits dramatically cheaper than round 1.

### Step 0.5.1 — Check codemap state and refresh aggressively

Look for `.codemap/` in the repo root. Four cases, all handled without asking permission unless a full rebuild is needed:

1. **No `.codemap/` directory at all.** First time auditing this repo. Tell the user, then invoke cartographer to build:
   > "No codemap exists yet. Running cartographer for a one-time full build — future audits will be much faster."

   For very large repos or slow machines, warn first and offer the option to fall back to grep for this round.

2. **`.codemap/` exists, state.json is recent** (within ~5 commits of HEAD, no uncommitted source changes). Codemap is fresh; proceed to Step 0.5.2.

3. **`.codemap/` exists but is somewhat stale** (5–50 commits behind, or has uncommitted changes). **Refresh automatically. Don't ask.**
   > "Codemap was 14 commits behind HEAD. Refreshed incrementally. 8 files updated; cross-references patched on 3 affected files. Continuing."

4. **`.codemap/` exists but is very stale or corrupt** (50+ commits behind, schema mismatch, malformed JSON). The one case where Cartographer asks first:
   > "Codemap is significantly stale (87 commits behind) or has schema drift. Recommend a full rebuild. Run it? (yes / fall back to grep / abort audit)"

### Step 0.5.2 — Check .gitignore policy

Confirm the user's commit policy for codemap and audit-log files. Read `.gitignore` and check whether `.codemap/` or `AUDIT_LOG.md` are excluded.

**Default policy for solo developers and small teams:** these should be committed (institutional memory). If `.gitignore` excludes them:
> "Noted: `.codemap/` is in .gitignore. The codemap won't be shared via git — every fresh clone will rebuild from scratch. That's fine if intentional. If you'd rather commit it (recommended for solo work and small teams), remove the entry."

Don't modify `.gitignore` automatically. Just inform.

### Step 0.5.3 — Spec version drift detection

Read the design spec (the doc the checklist was derived from) and find its version stamp. Read the codemap's `spec_refs` entries and check the version prefix.

If the spec has moved (e.g., v3 → v4) but the codemap still tags `spec_refs` with the old version:
> "Spec has moved from v3 to v4 since the codemap was last built. Asking cartographer to re-tag spec_refs from v3 to v4 where section numbers haven't changed. Sections that have moved in v4 will need manual review."

Cartographer handles the actual re-tagging; this phase just detects the drift and triggers it. If sections moved or renumbered, log the affected files for human review.

### Step 0.5.3b — Check codemap capabilities

Read `state.json.capabilities` (script-built codemaps record exactly what they produced). Before trusting any codemap field during Phase 3:

- A warning category is only "verified empty" if its detector appears in `capabilities.detectors_run`. Detector not listed → that check wasn't performed; do it inline or note it as uncovered.
- `imported_by` / `functions` data exists only for languages in `capabilities.import_extraction_languages` / `function_extraction_languages`. For other languages, fall back to grep.
- `capabilities.import_resolution: "best-effort-static"` means orphan and blast-radius data can have false positives/negatives — re-verify before citing in a finding (the existing hard rule already requires re-reading the file).

If `capabilities` is absent entirely, the codemap predates v0.5 — treat all warnings.json categories as best-effort and recommend a rebuild with the current template.

### Step 0.5.4 — Note codemap state in the audit log

Record:
> Codemap at audit start (YYYY-MM-DD):
> - State: fresh / refreshed incrementally / rebuilt / unavailable
> - Files mapped: N
> - Last refresh commit: abc123
> - Stages run: 1_tags, 2_spec_refs, 3_qualified_names [+ 4_call_graph if active]
> - Warnings present: 6 (1 high, 3 medium, 2 low)
> - Canonical designations: 2 clusters (4 stale candidates total)
> - Commit policy: codemap committed (or "codemap git-ignored")
> - Spec version: matches codemap tags / re-tagged from vN

### Step 0.5.5 — Surface high-severity warnings before Phase 1

If `warnings.json` has any **high-severity** warnings — especially duplicate filenames, backup directories, near-duplicate content, or ambiguous canonical designations — surface them prominently:

> "Heads up — cartographer flagged 1 high-severity warning:
> - `src/auth/refresh.ts` and `src/auth/refresh_v2.ts` are ~87% identical. Cartographer designated `refresh.ts` as canonical (it's imported by `workers/sync.ts`; `refresh_v2.ts` has no importers). Audit findings on `refresh_v2.ts` will be downgraded to Info pending your decision. Suggested fix: remove `refresh_v2.ts` or archive outside source tree."

For ambiguous canonical designations (cartographer couldn't decide which is current), the audit pauses and asks the user to resolve before proceeding. Findings on the wrong version of a file are noise. (Non-interactive runs can't pause — see "Non-interactive mode" below: treat both candidates as canonical and flag the ambiguity prominently in the log.)

### How Phase 3 will use the codemap

Phase 3 consults the codemap during checklist verification:

- *"Find every file tagged X"* → query `structure.json.files` filtered by tags
- *"What implements §X.Y?"* → query the `spec_refs` index in `structure.json` and `functions.json`
- *"What depends on file F?"* → read `dependencies.json[F].imported_by`
- *"Are there suspicious duplicates?"* → read `warnings.json.duplicate_basenames`, `near_duplicates`, `canonical_designations`
- *"What are the security-sensitive functions in this file?"* → filter `functions.json[file].functions` by tags
- *"What's the blast radius if I change this function?"* → read `functions.json[file].functions[fn].called_by` (recursive expansion as needed)
- *"Where's the canonical spec?"* → query `structure.json.files` for `doc_class == "spec"` and `is_canonical_spec: true`

**spec_refs format:** entries are objects, not strings:

```json
"spec_refs": [
  { "ref": "§8.1", "source": "explicit" },
  { "ref": "§3.7", "source": "inferred", "confidence": 0.85 }
]
```

When reading spec_refs, **treat explicit and inferred differently:**
- **Explicit refs**: trust them. Developer-authored intent.
- **Inferred refs at confidence ≥ 0.85**: trust them, but verify the first time you cite one in a finding (read the file + spec section to confirm).
- **Inferred refs at confidence 0.7–0.85**: useful as a starting point but always verify before citing.

**Hard rule:** the codemap directs attention but does not substitute for reading code. When recording a finding based on a codemap query, **re-read the actual file at the cited line** before writing the finding. Codemap data can be wrong or stale. No finding goes into `AUDIT_LOG.md` based purely on JSON.

### Step 0.5.6 — Codemap drift correction during the audit

If during Phase 3 the audit discovers that the codemap describes a file inaccurately (`purpose` wrong, function listed as `exported` is actually internal, `spec_refs` point at the wrong section), record this as a **codemap drift event**:

1. Logged under `codemap_drift` in `warnings.json` so future audits know about it
2. Inform the user with a suggested fix:
   > "Codemap drift detected: `src/auth/refresh.ts` is tagged with `spec_refs: ['§8.1']` but reading the file, it actually implements §8.2. Suggested fix: re-run cartographer or wait for next full refresh."

Drift correction is informational; it doesn't block the audit. Repeated drift on the same file suggests the codemap needs a more thorough refresh or the file is genuinely ambiguous.

---

## Phase 1 — Setup

**Goal:** make sure the repo has audit infrastructure. If it doesn't, create it. If it does, read it before proceeding.

### Step 1.1 — Look for existing infrastructure

Check the repo root for:
- `AUDIT_CHECKLIST.md` — categories and items checked during an audit
- `AUDIT_LOG.md` — durable history of past audit rounds and their findings
- A design spec (`DESIGN_SPEC.md`, `design.md`, `architecture.md`, project-specific filename) — the source of truth the checklist should derive from
- `.audit/acceptance-map.md` — the spec→acceptance-test mapping (Category 9; see `references/acceptance-mapping.md`)
- Pre-commit hooks (`.pre-commit-config.yaml`, `scripts/pre-commit.sh`, `.husky/`, etc.)

**Tell the user what was found and what's missing.** Be explicit:
> "Found AUDIT_CHECKLIST.md (147 items, last modified 3 weeks ago) and DESIGN_SPEC.md. No AUDIT_LOG.md — I'll create one. Found .husky/pre-commit; I'll read it to see what's already enforced automatically so I don't double-cover it."

### Step 1.2 — Confirm pre-commit-verification dividing line

Phase 0 has already established pre-commit is clean. In Phase 1, confirm what pre-commit covered so the audit doesn't waste effort re-checking it:
- `.pre-commit-config.yaml` (or equivalent)
- `.husky/` directory contents
- `scripts/pre-commit*` or `scripts/verify*`
- CI configs (`.github/workflows/`, `.gitlab-ci.yml`)

Tell the user the dividing line explicitly:
> "Pre-commit covers: tests (pytest), lint (ruff), typecheck (mypy), format (ruff format), secrets (gitleaks), build (npm run build). This audit will skip those entirely and focus on: schema correctness, data flow, security architecture, concurrency, resource bounds, spec compliance, operational readiness."

### Step 1.3 — Generate or refresh the checklist

**If no design spec exists at all, invoke the `spec-bootstrap` skill first.** A checklist generated from nothing is a generic lint pass, and "unspecified intent" is one of the deepest sources of residual errors. spec-bootstrap derives observed behavior from the code, interviews the user to separate intent from accident, and produces a §-numbered, provenance-marked spec; resume here after its sign-off. Two degraded paths:
- User declines the interview → proceed against spec-bootstrap's unconfirmed draft; provenance rules below govern grading.
- Headless run (no user available) → spec-bootstrap produces the draft without an interview; same rules.

**Provenance-aware grading for bootstrapped specs.** Statements carry `[confirmed]` / `[observed]` / `[assumed]` markers:
- `[confirmed]` violations → normal findings at normal severity.
- `[observed]` violations → normal findings, with a note that the baseline is observed behavior, not confirmed intent.
- `[assumed]` violations → **questions, not findings** (Phase 3.6 treatment). Flagging violations of guesses produces noise, and noise erodes trust in the audit.
Also pick up spec-bootstrap's "Known deviations" section — those are pre-seeded findings with user confirmation as evidence; carry them into this round.

If `AUDIT_CHECKLIST.md` doesn't exist, **generate it from the design spec.** Read the spec and extract every:
- `must`, `must not`, `never`, `always`
- Named invariant ("messages attach to X, not Y")
- Architectural decision ("Postgres only," "no auto-send")
- Confidence threshold or numeric bound (0.75 confidence, 12-month window)
- Promise to the user ("nothing deleted without confirmation")
- Schema constraint (foreign keys, uniqueness, status enum values)

Each becomes a checklist item. Group by category — see `references/checklist-categories.md` for the standard category set.

If the checklist exists but the spec has been updated since, **offer to refresh it** before auditing.

### Step 1.3b — Generate or refresh the acceptance map

If `.audit/acceptance-map.md` doesn't exist (and the repo has user-facing surfaces), generate it: extract the spec's **user-facing** musts and map each to the test that exercises it, per `references/acceptance-mapping.md`. Propose test matches by searching test names/descriptions — a match must assert the promise, not merely touch the feature. Rows with no asserting test are marked `UNMAPPED`; Category 9 grades them during Phase 3 (High for data-loss/security/privacy promises, Medium otherwise).

If the map exists but the spec version changed, regenerate it (keep the old one as `acceptance-map.<old-version>.md` for one cycle).

### Step 1.4 — Read the audit log

If `AUDIT_LOG.md` exists, read the most recent entries. This is the institutional memory across audit rounds:
- Which findings were fixed (don't re-flag them)
- Which findings were dismissed or deferred (with reasoning — respect those decisions)
- Which categories were covered last time and when
- Patterns in the codebase the previous auditor noticed

Surface anything relevant to the user before scoping:
> "Last audit (2 weeks ago, categories 1–3) flagged 14 issues; AUDIT_LOG shows 11 fixed, 2 deferred ('not v1 scope'), 1 still open (worker.rs:88 — backoff on DB reconnect). I'll re-verify that one as part of this round if you want."

---

## Phase 2 — Scope

**Goal:** agree explicitly with the user on what gets audited this round.

Audits fail when scope is implicit. "Run a deep audit" without scope is the root cause of the recurring-issues problem. Force the conversation.

### Step 2.1 — Propose a scope

Pick a scope based on context:
- **First audit of a project**: propose all categories, with a warning about size
- **Post-refactor**: propose the categories the refactor touched + one or two cross-cutting ones
- **Follow-up audit**: propose categories not yet covered, plus open items from previous rounds
- **Pre-release**: propose security, error handling, concurrency, resource bounds, spec compliance

Present it clearly:
> "Proposed scope for this audit round:
> - Category 1: Schema integrity (8 items)
> - Category 3: Security (12 items)
> - Category 5: Concurrency (7 items)
> - Plus: re-verify worker.rs:88 from last round
>
> Estimated time on my end: ~30 minutes of focused review. Categories 2, 4, 6, 7, 8 will be deferred to a later round. Sound right?"

### Step 2.2 — Wait for confirmation

Don't proceed without explicit user agreement. If they want "everything," push back gently:
> "I can do everything in one go, but I'll be honest: my best work on a large codebase comes from focused scope. Doing 3 categories thoroughly is more valuable than 8 categories at 40% depth. Want me to start with the 3 highest-risk categories and circle back?"

### Step 2.3 — Lock the scope

Once agreed, restate it before starting Phase 3. This is the contract for the round.

---

## Phase 3 — Execute

**Goal:** work through every checklist item in every scoped category. No skipping.

This is the heart of the skill. The execution discipline is what makes audits converge.

### Step 3.1 — One category at a time

Work categories sequentially, not in parallel. Within a category, work checklist items sequentially. Resist the urge to jump ahead when you notice something — note it, finish the current item, return.

### Step 3.2 — For each checklist item

1. **Identify the relevant files. Consult the codemap first:**
   - For "find every file with concern X" → query `structure.json` tags index, or `functions.json` for function-level tags
   - For "what touches spec section §X.Y" → query the `spec_refs` index
   - For "what depends on file F" → read `dependencies.json[F].imported_by`
   - For "are there suspicious duplicates affecting this check" → consult `warnings.json`

   If the codemap doesn't have the answer, fall back to grep/ripgrep/file-listings. Don't rely on memory.

2. **Open and read those files.** Actually read them — don't pattern-match from filenames, and **don't trust the codemap alone**. The bug is often in the file that *looks* fine in the codemap.

3. **Form a verdict:** one of:
   - **Verified clean** — checked, no issue found
   - **Finding** — with severity, file:line, description
   - **Cannot verify** — needs runtime info or user knowledge of intent
   - **Out of scope** — depends on something not in this round

4. **Record it immediately.** Don't trust memory.

5. **If the verdict came from the codemap, verify by re-reading the actual file.** Findings without file verification are not allowed in `AUDIT_LOG.md`.

### Step 3.3 — Severity definitions (apply strictly)

**Critical** — will definitely cause data loss, security breach, or unrecoverable user-facing failure in normal use. Examples: SQL injection, unencrypted credentials in logs, missing transaction around multi-table state change, auto-send path that bypasses user confirmation.

**High** — will likely cause significant problems under realistic conditions. Examples: race conditions between workers, missing index causing query timeouts on large data, error path that swallows exceptions, schema constraint missing where the spec requires it.

**Medium** — will cause problems in edge cases, or causes ongoing pain but isn't blocking. Examples: missing pagination on list query, awkward error messages, table that will grow unbounded but slowly, inconsistent naming.

**Low** — minor improvements; not bugs. Examples: code duplication, dead code, suboptimal patterns, missing documentation.

**Info** — observations that aren't findings but are worth noting. Examples: "This module is much larger than the rest; consider splitting before it grows further."

If a finding could be either of two severities, **pick the higher one and explain why.** Optimistic severity grading is how audits miss critical issues.

### Step 3.4 — Spec compliance is a first-class category

Don't just look for bugs; verify the code matches the spec. Every "must," "never," "always" from the spec is a checklist item. If the spec says "messages attach to account_contacts, never directly to persons" and the code has `message.person_id`, that's a finding regardless of whether it "works."

This is the category that catches the architectural drift pre-commit can never catch.

### Step 3.5 — Cross-cutting checks

Some checks span all categories:

- **No TODO/FIXME/XXX comments without an owner and date.** Findings: Medium.
- **No commented-out code blocks longer than 3 lines.** Findings: Low.
- **No `console.log`/`print`/`dbg!` left in non-test code paths.** Findings: Medium.
- **Every external dependency is pinned to a version, not floating.** Findings: Medium for prod deps, Low for dev deps.
- **No secrets in source files** (sanity-check on top of gitleaks). Findings: Critical.

Run these as a quick sweep at the start or end of each category.

### Step 3.6 — When unsure, ask

If a piece of code looks suspicious but you can't tell whether it's intentional, **ask the user** before flagging. Phrase as a question, not an accusation:
> "In `mail_sync.rs:142`, the retry loop catches all errors and continues without logging. This might be intentional (e.g., transient failures in a high-volume worker), or it might be hiding real problems. Which is it?"

Don't fabricate confidence. "I can't verify this without runtime info" is a legitimate verdict.

---

## Phase 4 — Report

**Goal:** produce a structured findings list the user can act on.

### Step 4.1 — Findings format

For each finding, produce:

```
## [Severity] Short title

**Category:** N — Category name
**Location:** path/to/file.ext:LINE (or range)
**Type:** spec-compliance | bug | safety | performance | concurrency | resource | UX | test-coverage | other
**Source:** static-review (default) | smoke-harness [N] | pre-commit

**Description:**
One short paragraph: what's wrong and why it matters.

**Evidence:**
- Code snippet or specific reference
- Spec reference if spec-compliance: "spec §3.2 — 'messages attach to account_contacts, never directly to persons'"
- Trace of how this fails (e.g., "if worker A inserts while worker B is reading, B sees partial state because there's no transaction")

**Blast radius:**
When the codemap is available, list what depends on this file/function. Example:
"14 files import this function. Fix will likely require coordinated updates in
`workers/sync.ts:42`, `api/login.ts:88`, and 12 others. See dependencies.json for the full list."

Skip this section when blast radius is small (≤2 dependents) or codemap unavailable.

**Suggested fix:**
One or two sentences. Don't write the patch — name the change.

**Effort estimate:** trivial / small / medium / large
```

### Step 4.1.1 — Stale-candidate downgrade rule

Before recording any finding, check `.codemap/warnings.json` for the file's status in `canonical_designations`:

- **Canonical** version of a cluster: record the finding normally with the severity it warrants.
- **Stale candidate** (non-canonical): downgrade severity to **Info** and reframe:
  > "Info: src/auth/refresh_v2.ts has [the original issue], but cartographer designated this file as a stale candidate (canonical: src/auth/refresh.ts). Verify whether this file is actually in use before treating as a real finding. If the file is dead code, the right fix is removal, not patching."

This prevents the audit from producing real-looking findings on code that probably isn't running.

**Exception:** if the stale candidate has `designation_reason: ambiguous`, the audit should have paused for user resolution in Phase 0.5.5. If for some reason it didn't, treat the file as canonical (better to over-flag than miss real findings on the running code) but note the ambiguity prominently.

### Step 4.2 — Order findings

Within the report:
1. All Critical findings first, in the order you'd want them fixed
2. Then High, ordered by effort (small fixes first so the user can ship quick wins)
3. Then Medium, grouped by category
4. Low and Info at the end, optionally collapsible

### Step 4.3 — Don't pad

If a category has zero findings, say "Category N: 0 findings, verified clean across all items." That's information, not a failure. Don't invent Low/Info findings to "balance" the report.

### Step 4.4 — Surface patterns

If multiple findings point at the same root cause, name the pattern explicitly:
> "Pattern observed: 6 of the 11 findings in Category 5 (Concurrency) trace to the same root cause — the worker pool doesn't take a row-level lock before status transitions. Fixing the pool will resolve them all together."

Patterns are higher-value than individual findings. Surface them.

---

## Phase 5 — Close

**Goal:** declare coverage, update the audit log, leave the repo ready for the next round.

### Step 5.1 — Coverage declaration

At the bottom of the report:

```
## Audit coverage declaration

**Scope this round:** Categories 1, 3, 5
**Checklist items covered:** 27 of 27 in scoped categories
**Items I could not verify (and why):**
  - Item 3.4.2 (token rotation under load) — requires runtime trace
  - Item 5.6.1 (worker recovery from crash) — would need a fault-injection test I didn't run

**Confidence:**
  - Critical findings in scoped categories: HIGH confidence none remain
  - High findings in scoped categories: HIGH confidence none remain
  - Medium findings: MODERATE confidence
  - Low/Info: not exhaustively pursued

**Out of scope this round:** Categories 2, 4, 6, 7, 8 — not covered, make no claims.

**Recommended next round:** Categories 2 (data flow) and 4 (error handling) — likely highest remaining risk.
```

The confidence declaration is what makes audits honest. Use it.

### Step 5.2 — Update AUDIT_LOG.md

Append a new entry:

```
## Audit run: YYYY-MM-DD, categories [N, M, ...]

**Pre-commit baseline at start:**
- Tests: [N passed / M failed]
- Lint / Typecheck / Build / Format: [clean | issues]
- Smoke/integration harness (per category):
  - [1+4] HTTP health: [PASS | FAIL: detail | SKIPPED | NOT SCAFFOLDED]
  - [2] dev/prod matrix: [PASS | FAIL: detail | ...]
  - [3] migration idempotency: [PASS | FAIL: detail | ...]
  - [5] webview e2e: [PASS | FAIL: detail | ...]
  - [7] launch-env probe: [PASS | FAIL: detail | ...]
  - [8] provider mocks: [PASS | FAIL: detail | ...]
  - [9] onboarding clickthrough: [PASS | FAIL: detail | ...]
- Harness failures converted to findings: [list of finding IDs, or none]
- Git: [clean | known-dirty paths]
- Commit at audit start: [SHA]

**Codemap state at start:**
- State: [fresh | refreshed incrementally | rebuilt | unavailable]
- Files mapped: [N]
- Last refresh commit: [SHA]
- Stages run: [1_tags, 2_spec_refs, 3_qualified_names, 4_call_graph?]
- Warnings: [N total: X high, Y medium, Z low]
- High-severity warnings carried forward: [list, if any]

**Scope:** [list]
**Findings:**
- [Severity] file:line — short title — [open | fixed | deferred | dismissed]
- ...
**Coverage declaration:** [link to or summary of declaration]
**Auditor notes:** anything worth flagging for next round
```

The pre-commit baseline and codemap state together make the audit reproducible — anyone reading the log later knows both the mechanical and structural state of the repo at audit time.

After the user fixes findings, they (or the audit-fix skill) update status from `open` to `fixed`. Deferred findings stay in the log with reasoning.

### Step 5.3 — Hand off to audit-fix

When the audit completes Phase 5 and there are open findings, mention audit-fix as the natural next step:

> "Audit complete. 14 findings recorded in AUDIT_LOG.md (1 critical, 3 high, 6 medium, 4 low). When you're ready to work through these, invoke audit-fix — it'll order the fixes by blast radius using cartographer's call graph, run pre-commit-verification after each fix, and re-audit when done to catch any regressions."

Note for the handoff: open `smoke-harness`/`pre-commit`-sourced findings mean pre-commit is *expected* to be red on those specific checks. That's fine — audit-fix's preflight treats failures matching open findings as its expected baseline, not as a blocker (the per-category results recorded in Step 0.3 are what it matches against).

Don't auto-invoke audit-fix. The user decides when to start fixing. They may want to:
- Review findings manually first
- Defer some findings to a later round
- Address a few critical issues by hand before invoking audit-fix
- Run audit-fix with a scoped subset

The audit's job ends at producing the findings list. audit-fix's job begins when the user asks for it.

### Step 5.4 — Recommend a cadence

Before signing off, suggest when the next audit should happen:
- After fixing this round's Critical and High findings
- After the next major feature lands
- Before a release
- Whatever fits the project's rhythm

The goal is for audits to feel routine and bounded, not crisis-driven.

---

## How this skill avoids the "endless audit rounds" problem

| Problem | Fix |
|---|---|
| Audits drift to whichever lens feels interesting that day | Phase 2 forces explicit scope agreement |
| Issues are sampled, not exhaustively found | Phase 3 works through every checklist item |
| Each round starts cold; previous fixes get re-flagged | Phase 1.4 reads AUDIT_LOG.md before starting |
| Severity is fuzzy, so users can't prioritize | Phase 3.3 defines severity strictly |
| Coverage is implied, so users assume "audit done = nothing left" | Phase 5.1 declares coverage and confidence explicitly |
| "Deep audit" means different things each time | The checklist defines depth, not a vibe |
| Audits run on broken builds find noise instead of real issues | Phase 0 requires pre-commit baseline first |
| Audits redo work pre-commit already does | Phase 0.3 + Phase 1.2 establish the dividing line explicitly |
| Retrieval by grep is slow and misses files | Phase 0.5 + Phase 3.2 use the codemap for targeted retrieval |
| Running app loads stale code; audit findings don't apply | Phase 0.5 surfaces high-severity warnings before audit proceeds |
| Audits flag the wrong version of duplicated files | Phase 4.1.1 downgrades findings on stale candidates |
| Untested code paths go unnoticed | Test-coverage category in the standard checklist set |
| Spec evolves but codemap and audit log still reference old version | Spec drift detection in Phase 0.5.3 |
| Codemap silently drifts from reality | Phase 0.5.6 drift correction + warnings.json.codemap_drift |

If the user is still seeing audit-after-audit find new things, check whether the skill is actually being followed end to end. Skipping Phase 0 (no clean baseline), Phase 0.5 (no codemap), Phase 1 (no checklist), Phase 2 (no agreed scope), or Phase 5 (no coverage declaration) reproduces the original problem.

---

## Non-interactive mode (driver / headless invocation)

When app-audit is invoked by an automation driver (e.g., the DevLoop driver) or any context where no user can answer mid-run, the confirmation gates get documented defaults instead of blocking:

- **Phase 2 scope agreement:** use the scope from the invoking prompt if one was given; otherwise carry over the open scope from the last audit round; otherwise (first audit) all categories. Log "scope auto-selected (non-interactive): [list]" instead of waiting for confirmation.
- **Phase 0.5.5 ambiguous canonical designations:** don't pause. Treat each ambiguous cluster's candidates as canonical (better to over-flag than miss findings on running code), record a High operational-readiness finding "ambiguous canonical designation needs human resolution," and continue.
- **Phase 3.6 "when unsure, ask":** record the verdict as **Cannot verify — needs user input**, with the question that would have been asked. Never guess.
- **Phase 1.3 checklist refresh offers / Phase 0.5.2 gitignore notes:** log the recommendation; don't wait.

Everything else — severity grading, the no-finding-without-reading-the-file rule, coverage declaration — is identical in both modes.

## Working with very large codebases

1. **The codemap is your friend.** Phase 0.5 builds it; Phase 3 queries it. You don't need to hold the whole codebase in context — just the parts the current checklist item touches.
2. **If the codemap is unavailable**, use grep/ripgrep/file-listing as the primary tool — not exhaustive file-reading. Build a map of where each concern lives before opening files.
3. **Audit by category, not by file.** A category's relevant files are usually a small fraction of the codebase.
4. **Keep an in-progress findings list** as a scratch file so it doesn't get lost when context fills up.
5. **If a category itself is too large**, split it (e.g., "Security — auth subsystem" vs "Security — data layer"). Update the checklist accordingly.

## Working with multi-language codebases

The skill is language-agnostic but some categories are language-specific. For each language present:
- Add language-specific items to the checklist (e.g., "Rust: no `unwrap()` on Result outside tests"; "TypeScript: no `any` in public API"; "Python: all async functions awaited")
- Note any language-specific tooling pre-commit already runs
- Verify spec compliance in each language's modules separately

## Output discipline

- **Don't summarize findings as "looks good overall."** Either declare coverage and confidence properly, or don't claim anything.
- **Don't list findings with vague locations** like "in the auth module." Always file:line.
- **Don't recommend fixes you can't justify.** If you say "use a row-level lock here," explain why.
- **Don't pad with Low/Info findings to make the report feel substantive.** A short, sharp report is better than a long, hedging one.

---

## Live audit panel (optional)

For long-running audits where the user wants real-time visibility into progress, an optional Streamlit panel reads `.audit/run_state.json` (which the audit updates throughout execution) and shows phase progress, codemap state, scope progress per category, the current item being checked, and findings as they accumulate.

The panel is most useful in Claude Desktop with substantial scope (3+ categories or 30+ items). For Claude Code (terminal), text-mode status blocks printed at phase transitions and every ~5 items are sufficient.

Either mode keeps `.audit/run_state.json` updated as the audit runs, so post-audit review and machine-readable history are always available.

Setup details, launch instructions, the Streamlit script, and the `run_state.json` schema: `references/live-panel-streamlit.md`.

---

## Reference files

- `references/checklist-categories.md` — the standard ten-category set with representative items, including test coverage (with acceptance mapping) and diagnosability. Read in Phase 1.3 when generating a checklist from a spec.
- `references/acceptance-mapping.md` — the `.audit/acceptance-map.md` format, lifecycle, and grading rules for the spec→test mapping. Read in Phase 1.3b and when verifying Category 9.
- `references/audit-log-template.md` — the format for AUDIT_LOG.md and AUDIT_CHECKLIST.md. Read in Phase 1.1 when creating these files for the first time.
- `references/severity-examples.md` — concrete examples of Critical / High / Medium / Low for common finding types. Consult when uncertain about severity grading.
- `references/live-panel-streamlit.md` — Streamlit panel template and `run_state.json` schema for live audit visibility. Optional; read this when launching the panel or writing the text-mode fallback.
