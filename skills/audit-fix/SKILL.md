---
name: audit-fix
version: 0.5.0
description: Address findings from a completed app-audit run, in safe order, with per-fix verification. Use whenever the user asks to fix the audit findings, address them, work through them, or run audit-fix. Reads AUDIT_LOG.md; uses cartographer's call graph (stage 4) to order fixes by blast radius — pure-local first, large-blast-radius last, critical severity prioritized within each tier. Runs pre-commit-verification after each fix; reverts and stops on failure. Refreshes cartographer and re-runs app-audit on the full original scope when done.
---

# Audit-fix

The remediation skill. Reads findings from a completed audit, addresses them in a safe order using cartographer's blast-radius data, verifies each fix before moving on, and closes the loop by re-auditing the same scope.

## Why this exists

The convergence problem in audits isn't just about finding issues — it's also about fixing them without introducing new ones. Common failures during remediation:

1. **Wrong fix order.** A fix to function X is made before its callers are updated; suddenly all callers break.
2. **No per-fix verification.** Several fixes are batched, then tests fail at the end; nobody knows which fix caused it.
3. **No regression check.** All findings get marked fixed; the user runs the app and discovers a new bug introduced by the fixes.
4. **Stale codemap.** Fixes happen, but the codemap and AUDIT_LOG aren't updated; the next audit sees an inconsistent state.

audit-fix addresses each:

- **Order by blast radius** (cartographer's `called_by` data) → safer fixes first
- **Per-fix verification with revert** → never propagate a regression
- **Re-audit the original scope after fixing** → close the loop
- **Refresh cartographer and update AUDIT_LOG.md** → state stays consistent

## When to use this skill

Trigger this skill when the user asks to:

- "Address them all" / "Fix them all" / "Fix the findings"
- "Run audit-fix" / "Audit-fix"
- "Address the audit findings"
- "Work through the findings"
- "Now fix them" (immediately after an audit completes)

**Prerequisites for the skill to run:**

- `AUDIT_LOG.md` exists with at least one open finding from the latest audit round
- Cartographer's `.codemap/` is present and reasonably fresh
- Cartographer stage 4 (call graph) is available — see Phase 0 step 0.7
- Pre-commit-verification is configured and currently passes
- Working tree is clean (no uncommitted changes that would conflict with fixes)

If any of these are missing, the skill explains what's needed and exits without making changes.

## Hard rules (apply across all phases)

These never relax:

1. **Never auto-apply schema migrations.** Always stop and ask. If a fix requires changing a `.sql` migration file or adding a new migration, surface the change for explicit user approval.
2. **Never modify `.gitignore`, `.env*`, `package.json`, `Cargo.toml`, or `pyproject.toml`** without explicit user approval. Dependency or config changes get a manual review step.
3. **Never push to remote.** All work is local. Local commits fine; pushing isn't.
4. **Never re-grade severity.** Audit decided; audit-fix executes. If the skill thinks a finding is worse than graded, append an auditor note — do not change the severity field.
5. **Never skip per-fix verification.** Every fix runs pre-commit before moving on.
6. **Never propagate a regression.** A failed verification → revert the single fix immediately → stop and ask the user.
7. **Never auto-fix newly-surfaced findings from the re-audit.** Reporting is in scope; remediation requires a new invocation.
8. **Never modify findings with status `deferred` or `dismissed`.** The user already decided.
9. **Never fix findings on stale-candidate files by patching.** The right fix is removing or renaming the file. If file removal hasn't been authorized, mark `deferred — file disposition pending`.

## The five-phase workflow

### Phase 0 — Preflight

**Goal:** confirm the audit-fix loop can run safely.

1. **Read `AUDIT_LOG.md`** and find the latest audit round (the most recent `## Audit run:` heading). Extract its findings list, severities, locations, current status (`open` | `fixed` | `deferred` | `dismissed`), and each finding's **`Source`** (`static-review` | `smoke-harness [N]` | `pre-commit`). AUDIT_LOG is the single source — app-audit folds pre-commit and smoke/integration harness results into it, so architectural findings and runtime/launch failures arrive here together. There is no separate pre-commit log to read.
2. **Filter to actionable findings:** anything with status `open`. Ignore the rest. Note each finding's source — it determines how Step 2.1 re-verifies it: `static-review` → re-read code; `smoke-harness`/`pre-commit` → re-run that specific check (behavioral findings can't be re-verified by reading code).
3. **Read `.codemap/state.json`** to confirm cartographer is fresh (refresh commit within ~5 of HEAD). If stale, **refresh cartographer silently** before continuing (per cartographer's self-refresh policy).
4. **Confirm pre-commit-verification passes.** Run it once at the start. If it fails:
   > "Pre-commit is failing before any fixes have been made. The repo isn't in a clean baseline. Fix the failing pre-commit checks first, then re-run audit-fix."
5. **Check working tree is clean.** If uncommitted changes:
   > "Working tree has uncommitted changes. Commit or stash them first, then re-run audit-fix."
6. **Detect partial prior fixes.** If any findings have status `open` but the cited file:line no longer matches the original code (someone fixed manually without updating the log):
   > "Finding 3.2 at auth.rs:88 is marked `open` but the code has changed since the audit. Re-verify before treating as fixable."
7. **Ensure cartographer stage 4 (call graph) has run.** Read `state.json.build_metadata.stages_run`. If it doesn't include `4_call_graph` or `4_call_graph_cached`, invoke cartographer with `--with-call-graph` before continuing:
   > "Cartographer hasn't run stage 4 (call graph). audit-fix's tier classification depends on `called_by` data. Running cartographer with --with-call-graph now (one-time cost ~30–60s)."

   Without stage 4, tier classification silently degrades to file-level only — which masks the blast radius the skill exists to surface. The whole point of audit-fix's order is the call graph; don't skip this step.

Report Phase 0 state:
> "Preflight complete. 14 open findings across 3 categories. Codemap fresh (stages 1–4 active). Pre-commit clean. Ready to plan."

### Phase 1 — Plan

**Goal:** order the fixes by safety, propose the plan, get user approval before any code changes.

#### Step 1.1 — Compute blast radius for each finding

For each open finding, query cartographer's codemap:

- **File-level blast radius:** count of `imported_by` entries on the file in `dependencies.json`
- **Function-level blast radius:** for findings cited at a specific function (file:line in a function's `loc_range`), count of `called_by` entries on that function in `functions.json`, recursively expanded one level

Findings on files in `warnings.json.canonical_designations[*].stale_candidates` are a special case — they get a "remove or rename the file" suggested fix rather than a code patch.

#### Step 1.2 — Classify each finding by blast radius

- **Tier 0 — pure local:** function has empty `called_by`, file has empty `imported_by` (or only test imports). Fix touches one function.
- **Tier 1 — same-file:** function's `called_by` are all in the same file. Fix may need to touch multiple functions in this one file.
- **Tier 2 — bounded cross-file:** function's `called_by` span 2–4 files. Fix needs coordinated edits across a small set.
- **Tier 3 — large blast radius:** 5+ dependent files. Fix needs careful planning and is high-risk.
- **Tier 4 — file removal:** the finding is on a stale-candidate file; the fix is removing/renaming the file, not patching it.

#### Step 1.3 — Order the fixes

Within tiers, sort by severity (Critical → High → Medium → Low → Info). Across tiers, fix lower-blast-radius first (Tier 0 → 1 → 2 → 3), with Tier 4 grouped at the end as their own batch.

The rationale: low-blast-radius fixes that are also critical-severity are the highest-leverage moves and least likely to introduce regressions. Going Tier 3 first risks cascading breakage that masks the actual root cause of later test failures.

Findings ordering is **not** strict 1, 2, 3 — it's by blast radius and severity. The user agreed to this.

#### Step 1.4 — Present the plan

Show the user the proposed order before doing anything:

```
Audit-fix plan — 14 findings, ordered by blast radius and severity:

TIER 0 (pure local, no dependents): 5 findings
  1. [Critical] auth/refresh.ts:88 — OAuth token in error log
  2. [High]     workers/categorize.rs:142 — missing transaction
  3. [High]     db/schema.sql:23 — missing NOT NULL constraint
  4. [Medium]   utils/format.ts:55 — wrong timezone handling
  5. [Medium]   logging/redact.ts:33 — incomplete redaction pattern

TIER 1 (same-file only): 3 findings
  6. [High]     auth/oauth_refresh.rs:208 — retry logic loses errors
                Same-file callers: 4 (all in oauth_refresh.rs)
  ...

TIER 2 (bounded, 2–4 files): 4 findings
  9. [High]     db/contacts.rs:90 — null handling
                Dependent files: workers/sync.rs, api/contacts.rs, ...
  ...

TIER 3 (large blast radius, 5+ files): 1 finding
  13. [Medium] core/event_bus.rs:55 — event ordering not guaranteed
               Dependent files: 14 (workers, routes, services)

TIER 4 (file removal): 1 finding
  14. [Info]   archive/old_auth.rs — stale candidate (per cartographer)
               Action: remove or move to archive/ subtree

Proceed with this plan? (yes / skip some / different order)
```

**Wait for user approval.** Common responses:

- "Yes" — proceed to Phase 2
- "Skip the medium-severity ones" — re-plan without them
- "Do tier 0 only for now" — limit scope
- "Reverse order" / "do tier 3 first" — re-order per user preference (warn them about regression risk)
- "Don't fix #14" — remove specific findings

Once user confirms, save the agreed plan to `.audit/audit-fix-plan.json` so it survives session restart.

### Phase 2 — Execute, one finding at a time

**Goal:** apply each fix, verify, move on. Never batch.

For each finding in the planned order:

#### Step 2.1 — Re-verify the finding

Re-verify **by the finding's source**, because behavioral findings can't be confirmed by reading code:

- **`static-review` findings:** re-read the file at the cited line. Confirm the issue described is still present.
- **`smoke-harness [N]` / `pre-commit` findings:** re-run that specific check (the smoke test, the migration idempotency script, the provider mock test, etc.). The finding is "present" if the check still fails. Reading the code is not enough — a migration can look correct and still fail the second run; a CORS layer can be registered and still emit the wrong header. The test is the oracle, not the source.

Three outcomes (either way):

- **Still present:** proceed to fix
- **Already fixed:** mark `fixed` in AUDIT_LOG.md with note "found already fixed at execution time" (for harness findings: "smoke check now passes"); move on
- **No longer findable:** the file has been refactored since audit; the finding may apply elsewhere or be moot. Mark `needs-re-audit` and move on without patching

#### Step 2.2 — Apply the fix

Make the fix. It should match the audit's suggested_fix where one was given, or be a minimal change that resolves the described issue. Apply in one logical commit — don't combine multiple unrelated fixes.

The hard rules from the top of this file apply here, especially:
- No schema migrations without explicit approval
- No changes to `.gitignore`, `.env*`, dependency manifests without approval
- Stale-candidate files get file-removal fixes, not patches

#### Step 2.3 — Run pre-commit-verification immediately

After each fix, run pre-commit-verification (or the equivalent: tests, lint, typecheck, build). Mandatory. No batching. Because pre-commit-verification now includes the smoke/integration harness, this per-fix run also re-runs the launch/integration tests — so a fix that resolves one smoke finding but breaks another launch path (e.g., fixing CORS but breaking migration idempotency) is caught immediately, not at the end.

**If pre-commit passes:** proceed to step 2.4. (For a `smoke-harness`-sourced finding, confirm the specific harness category that was failing now passes — that's the proof the fix landed.)

**If pre-commit fails:** the fix introduced a regression.

1. **Revert the fix** (`git checkout` or `git restore` on the changed files)
2. **Run pre-commit again** to confirm the baseline is restored
3. **Stop and report to the user:**
   > "Fix for finding [N] at [file:line] caused pre-commit to fail: [error]. Reverted the change. Pre-commit is clean again. What would you like to do?
   > - Skip this finding (mark `deferred`)
   > - Try a different fix approach (describe and I'll attempt)
   > - Pause audit-fix and let you investigate
   > - Continue with the next finding (leave this one open)"

The skill **does not** auto-skip and continue without asking. Per-fix verification means catching regressions immediately; the user decides how to handle.

#### Step 2.4 — Update AUDIT_LOG.md and commit

When a fix succeeds (pre-commit passes), update the finding's status in `AUDIT_LOG.md`:

```
- [Critical] auth/refresh.ts:88 — OAuth token in error log — fixed
  (audit-fix 0.4.0, commit abc1234, 2026-05-19T23:45:00Z)
```

**Default: one commit per fix** so `git log` reflects the audit-fix flow. The user can override with "batch the commits," but granular history is the default.

Commit message format:
```
audit-fix: [Severity] short description (finding N.M)

Fixes [finding location].
[1-2 lines on what changed.]

Audit round: [N], audit-fix 0.4.0.
```

#### Step 2.5 — Move to the next finding

Continue the loop until all planned findings are addressed or the user stops it.

### Phase 3 — Post-fix cartographer refresh

After Phase 2 completes (or pauses), **refresh cartographer** so the codemap reflects the new state. Run incrementally — only changed files re-process, so this is fast.

Report what changed:
> "Cartographer refresh: 8 files updated, 3 added to dependency edges, 1 new warning (an orphan function in workers/sync.rs)."

If the refresh surfaces new warnings (especially high-severity ones), flag them — these may be side effects of the fixes that need attention.

### Phase 4 — Re-run app-audit on the full original scope

Re-run app-audit on the **full original scope** — the same categories as the round that produced these findings. Not just touched files, not just touched categories. The full original scope.

The reason: regressions can land outside the directly-touched files (a refactor of a shared helper can break callers in unrelated categories). Limiting Phase 4 to "touched categories" produces a faster pass that misses the very cross-category regressions per-fix verification can't catch on its own.

Three possible outcomes:

1. **No new findings** — the fixes were clean. Report and proceed to Phase 5.
2. **New findings only on already-known issues** (deferred findings now visible because higher-severity ones cleared) — expected. Report as such.
3. **New findings introduced by the fixes** — the regressions per-fix verification missed (the kind that only show up after multiple changes interact). Surface prominently:
   > "Re-audit surfaced 2 new findings that weren't in the original round:
   > - [High] workers/sync.rs:88 — race condition (introduced by fix for finding 6)
   > - [Medium] api/contacts.rs:45 — null handling regression
   >
   > These appear to be caused by this audit-fix run. Want to address them now or in a new round?"

The skill does **not** auto-fix newly surfaced findings. Doing so would extend a remediation pass indefinitely. Let the user choose: another audit-fix invocation, manual fixes, or deferred to next round.

### Phase 5 — Report and close

Final summary, written as a new entry under the current audit round in `AUDIT_LOG.md`:

```
### Audit-fix pass — YYYY-MM-DD

**Audit-fix version:** 0.4.0
**Cartographer state:** stages 1–4 active, refreshed post-fix
**Findings addressed:** 12 of 14 planned (2 deferred per user)
  - Tier 0: 5 fixed cleanly
  - Tier 1: 3 fixed cleanly
  - Tier 2: 3 fixed (1 needed approach revision after first attempt failed pre-commit)
  - Tier 3: 1 deferred — risk too high for this round
  - Tier 4: 1 fixed (file removed: archive/old_auth.rs)

**Per-fix verification:** 1 fix failed pre-commit (finding 6.2); reverted and re-approached.
  Total revisions: 1.

**Re-audit result:** No new findings introduced. 2 previously-deferred findings now visible
  for next round.

**Commits made:** 12 (one per fix). See `git log --oneline` for details.

**Next recommended action:** Run audit again to verify clean baseline, or begin next round
  with remaining findings.
```

Recommend a next-step cadence:
- If everything cleared: "Recommend running audit again in 1–2 weeks or after the next major feature."
- If new findings surfaced: "Recommend a follow-up audit-fix pass on the new findings."
- If many findings deferred: "Recommend addressing deferred items before next audit."

## How audit-fix relates to the other skills

| Skill | Role |
|---|---|
| **cartographer** | Maintains the map. Produces `called_by` and `imported_by` data audit-fix uses for blast-radius ordering. Stage 4 is required for function-level tiering. |
| **app-audit** | Produces findings in `AUDIT_LOG.md`. audit-fix reads these. |
| **pre-commit-verification** | Runs after every fix. If it fails, audit-fix reverts and stops. |
| **audit-fix** | This skill. Reads findings, orders by blast radius, applies fixes with per-fix verification, refreshes cartographer, re-runs audit, updates log. |

The three audit-related skills form a closed loop:

```
build code
  → cartographer (map it; run stages 1–4)
  → app-audit (find issues)
  → audit-fix (resolve issues, verify, refresh map, re-audit)
  → if new findings: audit-fix again, or accept and continue
  → next code change
```

## Reference files

- `references/fix-ordering.md` — the safety-priority algorithm with worked examples, edge cases, and tiebreaks. Read this when planning the order in Phase 1.
- `references/per-fix-verification.md` — what pre-commit must do for each fix, how to detect partial vs total failure, revert mechanics. Read this when implementing Phase 2.
- `references/regression-detection.md` — how Phase 4 distinguishes "new finding caused by this fix" from "finding that was always there but got surfaced." Read this when interpreting Phase 4 results.

## Output discipline

- **Always present the plan in Phase 1** — never start fixing without explicit user approval.
- **Always run pre-commit after each fix** — non-negotiable.
- **Always update AUDIT_LOG.md** — keep the record honest.
- **Never claim "audit-fix complete"** unless the re-audit ran. If Phase 4 was skipped (user override), say "audit-fix pass complete; re-audit not run."
- **Always commit per-fix by default** — `git log` is the audit-fix trail. The user can override.
- **Always surface regressions prominently** — buried regression reports are the worst failure mode of an automated fix workflow.

## Standalone invocation phrases

Fresh invocation (after an audit):
- "Address them all"
- "Fix the findings"
- "Run audit-fix"
- "Now fix them"
- "Work through the findings"
- "Address the audit"

Continuation mode (resume an interrupted pass):
- "Resume audit-fix"
- "Continue addressing findings"
- "Pick up where we left off"
