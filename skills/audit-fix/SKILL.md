---
name: audit-fix
version: 0.15.0
description: Address findings from a completed app-audit run, in safe order, with per-fix verification. Use whenever the user asks to fix the audit findings, address them, work through them, or run audit-fix. Reads AUDIT_LOG.md; uses cartographer's call graph (stage 4) to order fixes by blast radius — pure-local first, large-blast-radius last, critical severity prioritized within each tier. Runs pre-commit-verification after each fix; reverts and stops on failure. Every fix is graded with a 0–1 truth score against an environment threshold (dev 0.90 / PR 0.95 / release 0.99) — below threshold, evidence is strengthened or the fix rolls back. Proof-tests are authored blind (from the finding + spec, never the fix diff). PR-scoped runs isolate fixes in a git worktree and use Conventional Commits. Closes with a tamper-proof clean-room re-run in a fresh worktree. Refreshes cartographer and re-runs app-audit on the full original scope when done.
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
- Cartographer stage 4 (call graph) is available — see Phase 0 step 0.8
- Pre-commit-verification is configured and passes **modulo known-open findings** (see Phase 0 step 4 — failures that ARE the open findings don't block; that would deadlock the loop)
- Working tree is clean (no uncommitted changes that would conflict with fixes)

If any of these are missing, the skill explains what's needed and exits without making changes.

## Hard rules (apply across all phases)

These never relax:

1. **Never auto-apply schema migrations.** Always stop and ask. If a fix requires changing a `.sql` migration file or adding a new migration, surface the change for explicit user approval.
2. **Never modify `.gitignore`, `.env*`, `package.json`, `Cargo.toml`, or `pyproject.toml`** without explicit user approval. Dependency or config changes get a manual review step.
3. **Never push to remote.** All work is local. Local commits fine; pushing isn't.
4. **Never re-grade severity.** Audit decided; audit-fix executes. If the skill thinks a finding is worse than graded, append an auditor note — do not change the severity field.
5. **Never skip per-fix verification.** Every fix runs pre-commit before moving on.
6. **Never propagate a regression.** A verification that surfaces a *new* failure (one not in the Phase 0 baseline of known-open findings) → revert the single fix immediately → stop and ask the user. Known-open failures from findings not yet fixed are expected and are not regressions.
7. **Never auto-fix newly-surfaced findings from the re-audit.** Reporting is in scope; remediation requires a new invocation.
8. **Never modify findings with status `deferred`, `dismissed`, or `suppressed`.** The user (or the team, via `.greenloopignore` / inline `greenloop:ignore` markers) already decided. A suppressed finding re-enters the queue only when its suppression expires or is removed — app-audit's Step 4.6 meta-audit handles that, not audit-fix.
9. **Never fix findings on stale-candidate files by patching.** The right fix is removing or renaming the file. If file removal hasn't been authorized, mark `deferred — file disposition pending`.
10. **Never mark a static-review finding `fixed` on self-review alone.** The model that wrote a fix is the worst judge of it. Critical/High static findings require adversarial re-verification (Step 2.3b); a fix whose proof is a new test requires that test to be proven able to fail (Step 2.3c).
11. **Never mark a fix `fixed` below the truth-score threshold.** Every fix is graded 0–1 on the strength of its verification evidence (Step 2.3d). Below the active threshold (dev 0.90 / PR 0.95 / release 0.99), either strengthen the evidence or roll the fix back — never ship it on a sub-threshold score.

## The five-phase workflow

### Phase 0 — Preflight

**Goal:** confirm the audit-fix loop can run safely.

1. **Read `AUDIT_LOG.md`** and find the latest audit round (the most recent `## Audit run:` heading). Extract its findings list, severities, locations, current status (`open` | `fixed` | `deferred` | `dismissed`), and each finding's **`Source`** (`static-review` | `smoke-harness [N]` | `pre-commit`). AUDIT_LOG is the single source — app-audit folds pre-commit and smoke/integration harness results into it, so architectural findings and runtime/launch failures arrive here together. There is no separate pre-commit log to read.
2. **Filter to actionable findings:** anything with status `open`. Ignore the rest. Note each finding's source — it determines how Step 2.1 re-verifies it: `static-review` → re-read code; `smoke-harness`/`pre-commit` → re-run that specific check (behavioral findings can't be re-verified by reading code).
3. **Read `.codemap/state.json`** to confirm cartographer is fresh (refresh commit within ~5 of HEAD). If stale, **refresh cartographer silently** before continuing (per cartographer's self-refresh policy). Also read `state.json.capabilities`: if the codemap was built by a script whose capabilities don't include the data a step needs (e.g., `canonical_designations` not in `detectors_run`, or a language missing from `import_extraction_languages`), don't trust the empty field — compute that piece inline (Read/Grep) or ask cartographer's direct path to fill it.
4. **Run pre-commit-verification once and capture the BASELINE.** Record every per-check result (existing checks + each harness category) as the baseline for this pass. Then classify any failures:
   - **Expected failures** — failures that correspond to an open finding in the audit log (match by harness category for `smoke-harness [N]` findings, by check name for `pre-commit` findings). These are *the things this pass exists to fix*. They do **not** block; without this rule, a harness finding would deadlock the loop (the audit converts the failure into a finding, then audit-fix refuses to start because the failure makes pre-commit red).
   - **Unexpected failures** — failures with no corresponding open finding (broken build, failing unit tests, a harness category nobody flagged). These DO block:
   > "Pre-commit has failures that don't correspond to any open finding: [list]. The repo isn't in a known baseline. Fix those first (or run app-audit so they become findings), then re-run audit-fix."

   Save the baseline (per-check pass/fail) to `.audit/audit-fix-baseline.json` — Step 2.3 compares against it.
5. **Check working tree is clean.** If uncommitted changes:
   > "Working tree has uncommitted changes. Commit or stash them first, then re-run audit-fix."
6. **Detect partial prior fixes.** If any findings have status `open` but the cited file:line no longer matches the original code (someone fixed manually without updating the log):
   > "Finding 3.2 at auth.rs:88 is marked `open` but the code has changed since the audit. Re-verify before treating as fixable."
7. **Read the chronicle if present** (`.audit/CHRONICLE.md` — app-audit's
   self-learning layer). Two sections matter to fixing: **lessons** (env vars
   tests need, intentional oddities the user already confirmed — these prevent
   "fixing" something that's deliberate) and **fix lessons** from prior passes
   (approaches that failed for a recurring pattern, so they aren't retried).
   Missing file → skip silently.
8. **Ensure cartographer stage 4 (call graph) has run.** Read `state.json.build_metadata.stages_run`. If it doesn't include `4_call_graph` or `4_call_graph_cached`, invoke cartographer with `--with-call-graph` before continuing:
   > "Cartographer hasn't run stage 4 (call graph). audit-fix's tier classification depends on `called_by` data. Running cartographer with --with-call-graph now (one-time cost ~30–60s)."

   Without stage 4, tier classification silently degrades to file-level only — which masks the blast radius the skill exists to surface. The whole point of audit-fix's order is the call graph; don't skip this step.

Report Phase 0 state:
> "Preflight complete. 14 open findings across 3 categories. Codemap fresh (stages 1–4 active). Pre-commit baseline captured: 2 expected failures (harness [3] migration idempotency, harness [2] dev/prod matrix — both are open findings), 0 unexpected failures. Ready to plan."

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

Within tiers, sort by **severity, then provenance, then confidence**: Critical → High → Medium → Low → Info; within a severity, `new` (regression introduced by the change under review) before `pre-existing`; within that, higher-confidence findings first. Across tiers, fix lower-blast-radius first (Tier 0 → 1 → 2 → 3), with Tier 4 grouped at the end as their own batch.

The rationale: low-blast-radius fixes that are also critical-severity are the highest-leverage moves and least likely to introduce regressions. Provenance breaks ties toward fixing the regression the user just introduced before older debt. Going Tier 3 first risks cascading breakage that masks the actual root cause of later test failures.

**Skip advisory/low-confidence items by default.** Findings the audit demoted to advisory in Phase 4.5 (ungrounded, or confidence < 0.5) are *not* auto-fixed — list them separately as "needs confirmation" and ask the user before touching them. audit-fix executes grounded findings; it doesn't act on hunches.

Findings ordering is **not** strict 1, 2, 3 — it's by blast radius, severity, and provenance. The user agreed to this.

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

Use a **Conventional Commit** message so changelog/release tooling stays clean:
`<type>(<scope>): <summary> (greenloop)`. Type from the finding category —
`fix` for bug/safety/concurrency/security, `perf`, `test`, `refactor`, `docs`;
scope = the audit category or module.

**PR-scoped runs → isolate fixes in a worktree.** When audit-fix is invoked on
a PR/diff review (the audit round was change-scoped), don't mutate the user's
working tree. Create a dedicated worktree off the base ref, apply + per-fix
verify there, and on success push a `greenloop/fix-…` branch or open a fix PR;
on failure remove the worktree. Recipe: `references/pr-review.md` §5. For a
plain local audit (the common case), apply in place as before.

The hard rules from the top of this file apply here, especially:
- No schema migrations without explicit approval
- No changes to `.gitignore`, `.env*`, dependency manifests without approval
- Stale-candidate files get file-removal fixes, not patches

#### Step 2.3 — Run pre-commit-verification immediately, compare against the baseline

After each fix, run pre-commit-verification (or the equivalent: tests, lint, typecheck, build). Mandatory. No batching. Because pre-commit-verification now includes the smoke/integration harness, this per-fix run also re-runs the launch/integration tests — so a fix that resolves one smoke finding but breaks another launch path (e.g., fixing CORS but breaking migration idempotency) is caught immediately, not at the end.

**Interpret the result against the Phase 0 baseline, not as a bare pass/fail.** While other findings remain open, their checks are still expected to fail — a red result is only a regression if it's *new*. Classify each failing check:

- **Known-open failure** (in the baseline AND still corresponds to an open finding): expected. Not a regression. Continue.
- **Target check still failing** (the check this fix was supposed to resolve): the fix didn't land. Revert, count as a failed attempt, and re-approach or ask the user (headless: defer after the attempt limit — see "Non-interactive mode").
- **New failure** (passed in the baseline, or was already fixed earlier in this pass and now fails again): **regression.** Trigger the revert flow below.

After classifying, update the baseline: when a fix lands, its check moves to "must pass" — re-breaking it later in the pass is a regression, not a known-open failure.

**If there are no new failures and the target check passes:** proceed to step 2.4. (For a `smoke-harness`-sourced finding, the specific harness category passing is the proof the fix landed.)

**If there is a new failure:** the fix introduced a regression (revert flow below).

#### Step 2.3b — Adversarial re-verification (static-review findings)

Harness/pre-commit findings have a real oracle: the check passes or it doesn't. Static-review findings don't — "fixed" means the model that wrote the fix re-read its own code and approved it. That self-grading is one of the two main ways "the AI said it was fixed" turns out false (the other is vacuous tests, Step 2.3c).

So after pre-commit passes, **try to refute the fix** before marking the finding fixed. Full protocol: `references/adversarial-verification.md`. The short version:

- **Where subagents are available** (e.g., Claude Code's Task/Agent tool): spawn an independent verifier with ONLY the original finding text and the file paths — *not* the fix diff, *not* the rationale. Its question is "is this issue present in the current code?" If it finds the issue (same line, another instance, or a variant the fix missed) → the fix is incomplete: treat like "target check still failing" (revert or extend, count a failed attempt).
- **Where subagents aren't available**: run the structured self-refutation pass from the reference — re-derive the finding from the description alone, then check the four standard escape routes (other instances of the same pattern, cosmetic fix, narrower-than-the-finding fix, adjacent invariant broken).

**Cost discipline:** mandatory for Critical and High static findings; sample at least one per category for Medium; skip for Low/Info. Record the verdict in the log entry: `re-verified: adversarial (independent) — no refutation` or `re-verified: self-refutation pass`.

**The independent verifier can be a different provider entirely.** When a
second-model CLI is available (codex / gemini / ollama) and the cross-provider
privacy gate has been cleared (app-audit's `references/multi-model.md` §0), a
cross-model challenge is *stronger* independence than a same-family subagent —
different training, different blind spots — and counts as `independent` for
the truth score's S3 signal (local models at half weight, named in the log).
At the **release threshold (0.99)** with consensus mode on (`GREENLOOP_CONSENSUS=1`
or the user asked for multi-model review), Critical/High fixes must survive
the cross-model challenge in addition to the internal one; no provider
available → report "consensus requested but no provider available", never
silently lower the bar.

#### Step 2.3c — Prove the test can fail (when a fix adds or leans on a test)

A test written alongside a fix, by the same model, frequently passes for the wrong reason — it asserts too little, mocks away the behavior under test, or tests the fix's implementation rather than the finding's behavior. A green test only counts as evidence if it's red when the bug is present.

**Author the proof-test blind.** When the fix needs a NEW test as its oracle, the test is written from the **finding text + the spec section + the function's public signature** — never from the fix diff or the patched implementation. A test that can see the fix tends to assert what the fix *does*, not what the finding *requires*; blind authoring breaks that anchoring (the mumei discipline). Where subagents are available, dispatch a test author that receives only those three inputs; otherwise, write the test *before* re-reading the patched code, from the finding description alone. Once proven red-green, the test is **frozen**: if the fix later iterates and the blind test disagrees with it, the fix is wrong (or the spec is — stop and ask the user). Never edit the proof-test to make a fix pass. Full contract: `references/verification-depth.md` §4.

When the fix added/modified a test, or the finding's "fixed" status rests on a test as its oracle:

1. Temporarily restore the buggy behavior (reverse-apply the *non-test* part of the fix; mechanics in `references/adversarial-verification.md`).
2. Run the test. **Expect FAIL.**
3. Restore the fix; run the test again. Expect PASS.
4. If step 2 *passed* with the bug present → the test is vacuous. The finding stays open; fix the test first, then redo this step.

Record in the log: `test-oracle proven: red-green verified (blind-authored)` / `test-oracle proven: red-green verified` or `test-oracle NOT proven: <why> — finding remains open`.

#### Step 2.3d — Truth score: grade the evidence, then gate on the threshold

A fix isn't "verified" or "unverified" — verification has *strength*. A harness check flipping red→green is strong evidence; a self-review of one's own patch is weak. Step 2.3d makes that explicit: score the evidence 0–1, compare against the threshold for where this fix is headed, and never let a weakly-verified fix ride a strong-sounding "fixed" status.

**Score = sum of the signals that actually ran** (full rubric and worked examples: `references/verification-depth.md` §1):

| Signal | Weight |
|---|---|
| Target oracle passed (the check/test that proves THIS finding is resolved) | 0.50 |
| No new failures across the full verification surface vs. baseline (Step 2.3) | 0.20 |
| Adversarial re-verification (Step 2.3b): independent subagent 0.15 / self-refutation 0.08 | ≤ 0.15 |
| Test oracle proven red-green (Step 2.3c). Granted by construction for harness/pre-commit findings — the check was red before the fix and green after, which IS a red-green proof | 0.10 |
| Fix is minimal and in-scope (touched only files within the finding's blast-radius tier; no drive-by edits) | 0.05 |

**Thresholds by destination** (where the fix is going, not how it feels):

| Environment | Threshold | Detected when |
|---|---|---|
| dev (default) | **0.90** | plain local audit-fix run |
| PR / shared branch | **0.95** | change-scoped run (Step 2.4 PR mode), or fixes land on a branch with an open PR |
| release / main-bound | **0.99** | user says release/ship/tag, or the fix targets the default branch |

User override always wins (an explicit "use threshold X" or `GREENLOOP_TRUTH_THRESHOLD`). The defaults mean: a dev fix needs at least a self-refutation pass; a PR fix needs an independent adversarial check; a release fix needs every signal — independent verification, a proven oracle, and a clean minimal diff.

**Below threshold → strengthen first, roll back second.** A sub-threshold score usually means *missing evidence*, not a bad fix — so the first response is to run the missing verification (dispatch the independent verifier, prove the oracle red-green), which is almost always cheaper than rewriting the fix. Only when the evidence can't be strengthened — the adversarial check WEAKENED the fix, the oracle can't be proven, the diff can't be narrowed — **revert the fix** (auto-rollback), mark the finding `open` with note `truth score N.NN < T.TT (<env> threshold) — evidence insufficient`, and treat it as a failed attempt (re-approach or ask the user; headless: defer after the attempt limit).

Record the score in the log entry: `truth score: 0.93 (oracle 0.50 + surface 0.20 + adversarial-self 0.08 + red-green 0.10 + minimal 0.05) ≥ 0.90 dev threshold`.

#### The revert flow

Triggered by a **new failure** in Step 2.3 (regression), or by a sub-threshold truth score in Step 2.3d that couldn't be strengthened:

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
  (audit-fix <version from this file's frontmatter>, commit abc1234, 2026-05-19T23:45:00Z)
```

**Default: one commit per fix** so `git log` reflects the audit-fix flow. The user can override with "batch the commits," but granular history is the default.

Commit message format:
```
audit-fix: [Severity] short description (finding N.M)

Fixes [finding location].
[1-2 lines on what changed.]

Audit round: [N], audit-fix <version from this file's frontmatter>.
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

The re-audit also spot-checks `fixed` statuses: any Critical finding closed with only `re-verified: self-refutation pass` (no independent verifier was available) gets re-checked first.

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

#### Step 5.0 — Clean-room close (tamper-proof re-run)

Before writing the final summary, re-run the verification surface **in a fresh
worktree of HEAD** — committed state only, none of this session's uncommitted
residue. Per-fix verification ran in the working tree, where a stray local file,
an edited test, or an env var can quietly rig a green verdict; the clean-room
run is the proof that *what was actually committed* is green. This is
pre-commit-verification's clean-room mode (recipe:
`references/verification-depth.md` §3) — run it **once per pass**, not per fix.

- **Clean-room green** → record `clean-room: PASS (worktree @ <sha>)` and continue.
- **Clean-room red where the working tree was green** → something uncommitted
  was load-bearing (a file never committed, a rigged test, local config).
  Surface it prominently and treat the affected fixes as NOT verified — their
  truth scores drop and the findings reopen. Do not close the pass green.

When the clean-room run passes, optionally write the **signed witness
manifest** (`.audit/witness/<timestamp>.json` — commit SHA, per-check results,
truth scores, skill versions, signed with a local Ed25519 key via
`ssh-keygen -Y sign`). It makes "this commit verified green" a checkable,
tamper-evident claim instead of a log line. Recipe and verify command:
`references/verification-depth.md` §5. Skip silently if the user doesn't want
key material created.

#### Step 5.1 — Final summary

Written as a new entry under the current audit round in `AUDIT_LOG.md`:

```
### Audit-fix pass — YYYY-MM-DD

**Audit-fix version:** <version from this file's frontmatter>
**Cartographer state:** stages 1–4 active, refreshed post-fix
**Findings addressed:** 12 of 14 planned (2 deferred per user)
  - Tier 0: 5 fixed cleanly
  - Tier 1: 3 fixed cleanly
  - Tier 2: 3 fixed (1 needed approach revision after first attempt failed pre-commit)
  - Tier 3: 1 deferred — risk too high for this round
  - Tier 4: 1 fixed (file removed: archive/old_auth.rs)

**Per-fix verification:** 1 fix failed pre-commit (finding 6.2); reverted and re-approached.
  Total revisions: 1.

**Truth scores:** 12 fixes ≥ 0.90 (dev threshold); range 0.90–1.00, median 0.93.
  1 fix initially 0.85 — strengthened with independent adversarial re-verification → 0.93.

**Clean-room re-run:** PASS (fresh worktree @ abc1234 — committed state verified green).
**Witness:** .audit/witness/2026-06-12T2145Z.json (Ed25519-signed) — or "not written".

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

#### Step 5.2 — Contribute fix lessons to the chronicle

Append to `.audit/CHRONICLE.md` (under `## Fix lessons` — format:
app-audit's `references/self-learning.md` §1) anything the NEXT pass would
otherwise pay to rediscover:

- **Failed approaches**: "finding-pattern X: tried <approach>, broke <check> —
  worked instead: <approach>". This is what stops a future pass from retrying
  a known-bad fix on a recurring pattern.
- **Environment gotchas discovered while verifying** (env vars the tests need,
  services that must be stopped, the clean-room delta if Step 5.0 found one).
- **Intentional behavior confirmed by the user** during this pass ("the
  double-write in sync.rs is deliberate — offline queue") — these prevent the
  same question being asked round after round.

Only durable lessons — not a narration of the pass (AUDIT_LOG already has
that). One or two lines each; skip the step entirely when nothing qualifies.

#### Step 5.3 — Refresh the reporting artifacts

The fix pass changes finding statuses, so the reporting surface app-audit
maintains must follow (formats: app-audit's `references/workflow-reporting.md`):

- **`TECHNICAL_DEBT.md`** — remove entries whose findings got fixed this pass;
  add entries for findings newly `deferred` (with the deferral reason and
  round). New debt deserves one explicit line in the final summary — deferring
  is a decision, not a default.
- **`.audit/status.json`** — update the finding counts and append a
  `fix_pass` event to the current round's history entry (fixed/deferred/
  reverted counts, truth-score stats, clean-room result).

Skip silently if neither file exists (the repo hasn't adopted the reporting
layer).

## Live fix progress (Selran Hub panel)

Probe once at Phase 0: `curl -s -m 0.3 http://127.0.0.1:11999/hub/health`. If `"hub":"selran"` with `"audit"` in capabilities, create a run (`POST /v1/audit/runs` with `{"title": "audit-fix — <repo>", "repo": "<repo>"}`), tell the user the URL once, and stream progress to `POST /v1/audit/runs/<id>/events`. **All Hub POSTs must include the header `X-Selran-Local: 1`** (the Hub refuses mutations without it):

- when the plan is approved: one `{"type":"note","text":"plan: N findings across M tiers"}`
- after each finding resolves: `{"type":"fix","title":"<finding title>","status":"fixed|deferred|reverted|failed","location":"file:line"}`
- at close: `{"type":"complete","summary":"<X fixed, Y deferred>"}`

Posting failures are silently ignored — the panel never blocks the fix loop. Hub absent → skip silently (the once-per-session mention rule belongs to app-audit; don't double-mention).

## Non-interactive mode (driver / headless invocation)

When audit-fix is invoked by an automation driver (e.g., the DevLoop driver) or any context where no user is available to answer questions, the interactive gates get documented defaults instead of blocking:

- **Phase 1.4 plan approval:** auto-approve the computed plan as-is (it is already the safe order). Log "plan auto-approved (non-interactive)" in AUDIT_LOG.md.
- **Step 2.3 failures:** after a failed fix attempt, retry once with a different approach; after **2 failed attempts** on the same finding, revert, mark it `deferred — attempts exhausted (non-interactive)`, restore the baseline, and continue with the next finding. Never loop on one finding.
- **Hard-rule approvals (schema migrations, dependency/config manifests, file removal):** these never get auto-approved. Mark the finding `deferred — requires user approval` and continue. The hard rules hold in every mode.
- **Phase 4 newly-surfaced findings:** report only, exactly as in interactive mode. Never auto-fix.

Detect the mode from context: an explicit instruction in the invoking prompt ("mark deferred and continue", "do not ask"), or an environment where asking is impossible. When in doubt, ask once — if no answer is possible, fall back to these defaults and say so in the log.

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
- `references/adversarial-verification.md` — the independent-refutation protocol for static findings (with and without subagents) and the red-green proof for test oracles. Read this when executing Steps 2.3b / 2.3c.
- `references/verification-depth.md` — the truth-score rubric with worked examples, threshold detection, the strengthen-then-rollback procedure, the clean-room worktree recipe, the blind property-authoring contract, and the signed witness manifest. Read this when executing Steps 2.3d / 5.0.
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

**Crash recovery (how continuation actually works).** A pass interrupted by
session death loses nothing — its state is already on disk:

1. `.audit/audit-fix-plan.json` — the user-approved plan and order (Step 1.4).
2. `.audit/audit-fix-baseline.json` — the Phase 0 per-check baseline.
3. `AUDIT_LOG.md` finding statuses + the per-fix commits in `git log`
   (one commit per fix is the default precisely so recovery is unambiguous).

On resume: re-read all three, find the first planned finding that is neither
`fixed` nor `deferred`, verify the working tree is clean (a half-applied fix
from the dead session → `git status` shows it → revert it first, count as a
failed attempt), update the baseline for fixes that already landed (their
checks moved to must-pass), and continue the Phase 2 loop from there. Never
re-ask plan approval for an already-approved plan; re-confirm only if HEAD
moved by commits that aren't this pass's own fix commits.
