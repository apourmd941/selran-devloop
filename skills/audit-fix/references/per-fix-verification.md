# Per-Fix Verification

After every single fix, audit-fix runs pre-commit-verification and waits for the result before moving on. This is mandatory and non-negotiable — it's the mechanism that catches regressions immediately rather than at the end of a 14-fix batch.

This file documents what pre-commit must do, how to detect partial vs total failure, and the revert mechanics when verification fails.

---

## What "pre-commit-verification" means in this context

audit-fix invokes the user's existing pre-commit setup. There's no single command — different projects configure pre-commit differently. The skill should detect what's configured:

1. **`.husky/pre-commit`** (Node projects) — run via `.husky/pre-commit` or by inspecting and invoking the same scripts
2. **`.pre-commit-config.yaml`** (Python `pre-commit` framework) — run via `pre-commit run --all-files`
3. **`scripts/pre-commit.sh`** or similar — run via the script
4. **A pre-commit-verification skill** — if the user has one installed, invoke it

audit-fix doesn't define what pre-commit should check. It expects pre-commit to cover:

- **Unit tests** (`cargo test`, `npm test`, `pytest`, etc.)
- **Integration tests** when configured
- **Lint** (`clippy`, `eslint`, `ruff`)
- **Type-check** (`tsc --noEmit`, `mypy`, `cargo check`)
- **Build** (`cargo build`, `npm run build`)
- **Format** (`cargo fmt --check`, `prettier --check`, `black --check`)
- **Smoke checks** (boots and responds to health, etc., per project)

If a project's pre-commit doesn't run tests, audit-fix should warn at Phase 0:

> "Detected pre-commit configuration but it doesn't appear to run the test suite. Per-fix verification will catch lint/typecheck/build issues but won't catch test failures. Recommend extending pre-commit to include `npm test` (or equivalent) for full safety."

The user can choose to proceed without — but they've been told.

---

## When to run pre-commit

After every single fix. No batching, no exceptions:

```
Apply fix N
  ↓
Run pre-commit
  ↓
Pass? → mark finding fixed, commit, proceed to fix N+1
Fail? → revert, report, ask user
```

The exception is **explicit user override**: if the user says "batch the fixes and verify at the end" the skill complies, but warns:
> "Batching means a regression introduced by an early fix won't be caught until all fixes are applied. If pre-commit fails at the end, isolating the cause may require git bisecting through the commits. Proceed with batching?"

---

## Detecting failure modes

Pre-commit can fail in different ways, each requiring different response.

### Failure type 1 — Test failure

Example: `cargo test` exits non-zero, with output naming the failing test.

**Response:** revert the fix, report the test failure to the user with the test name and any output the test produced.

```
Fix for finding 6 (auth/refresh.ts:88) was applied and reverted.

Pre-commit failed: 1 test failed
  - tests/auth_integration::refresh_token_returns_error_on_invalid
    expected: Err(TransientError)
    got:      Ok(TokenPair)

This suggests the fix changed behavior in a way the existing test catches.
Options:
  1. Try a different approach to the fix (describe)
  2. Update the test to match the new behavior (if the test was wrong)
  3. Skip this finding (mark deferred)
```

### Failure type 2 — Lint or typecheck failure

Example: `cargo clippy` flags a new warning that the user's config treats as error; or `tsc` finds a type mismatch.

**Response:** revert, report the specific lint/type issue. Often these are easily fixable — the skill can offer to address them as part of the same fix:

```
Fix for finding 4 (frontend/src/components/InboxList.jsx:142) caused 2 typecheck errors:
  - line 145: argument of type 'string' not assignable to parameter of type 'Date'
  - line 148: property 'sortKey' does not exist on type 'InboxItem'

Want me to try an extended fix that addresses these, or revert and try a different approach?
```

### Failure type 3 — Build failure

Example: `cargo build` fails because the fix changed a function signature that another file expects unchanged.

**Response:** revert, report the build error. This is often a signal that blast-radius analysis missed something — the fix has dependents that need updating.

```
Fix for finding 9 (db/contacts.rs:90) caused a build failure:
  workers/sync.rs:142: cannot find method `find_by_email_lowercase` on type `Contact`
  api/contacts.rs:88: function signature mismatch

These callers need coordinated updates. Cartographer's blast-radius estimate may have been
incomplete. Options:
  1. Extend the fix to update these callers (I'll attempt)
  2. Revert and address as a multi-file change in next round
  3. Skip this finding
```

### Failure type 4 — Build / smoke check failure

Example: build succeeds but the boot test fails — app crashes on startup.

**Response:** revert immediately, report. This is usually a runtime regression (config / initialization / migration). Often needs human investigation:

```
Fix for finding 11 (config/loader.rs:23) passed build and tests but failed smoke check:
  backend-rs boot test exited with: thread 'main' panicked at 'config key missing: API_KEY'

The fix may have changed config requirements. Recommend investigating manually before
re-attempting.
```

### Failure type 5 — Pre-commit infrastructure failure

Example: pre-commit itself errored (couldn't find a tool, ran out of memory, network timeout).

**Response:** don't revert the fix — the underlying code might be fine; we just couldn't verify. Report:

```
Pre-commit infrastructure failed (not the code):
  pre-commit: command not found: npm

Cannot verify the fix for finding [N]. The change is currently uncommitted.
Options:
  1. Pause audit-fix; fix the pre-commit setup; resume
  2. Skip per-fix verification and proceed (risky — regressions won't be caught)
  3. Revert the uncommitted fix and stop the audit-fix pass
```

---

## Revert mechanics

When a fix needs reverting, do it cleanly:

### Single-file fix

```bash
git restore <file>
# Or if not yet staged:
git checkout -- <file>
```

Then verify the revert succeeded by running pre-commit again. If pre-commit *still* fails after revert, the failure was pre-existing — the fix wasn't the cause. Surface this:

```
Reverted the fix but pre-commit still fails:
  [same error]

This failure pre-existed the audit-fix run. Phase 0 should have caught this but didn't.
The repo baseline is now unclean. Recommend:
  1. Investigate the pre-existing failure
  2. Re-run audit-fix from scratch once baseline is clean
```

### Multi-file fix

If a fix modified multiple files:

```bash
git restore <file1> <file2> <file3>
```

Or roll back via `git reset --hard HEAD` if the fix was already partially committed (rare but possible if the user opted into per-fix commits):

```bash
git reset --hard HEAD~1
```

The skill always confirms with the user before doing destructive operations:
> "About to `git reset --hard HEAD~1` to revert the just-committed fix. This is irreversible from the audit-fix perspective. Proceed?"

### Staged-but-not-committed changes

The cleanest case. `git restore --staged <file>` followed by `git restore <file>` removes both the staging and the working-tree change.

---

## After reverting — confirm baseline

Always re-run pre-commit after a revert to confirm the baseline is clean. This catches the case where the fix introduced *one* regression but reverting also exposed a *different* pre-existing issue:

```
Fix applied. Pre-commit: FAIL (test X)
Revert applied. Pre-commit: PASS  ← baseline confirmed clean, proceed
```

vs.

```
Fix applied. Pre-commit: FAIL (test X)
Revert applied. Pre-commit: FAIL (test Y, different from X)  ← something else broken, escalate
```

The second case means audit-fix can't safely continue without user intervention. Stop the entire pass and surface the situation.

---

## Tracking verification state

For each finding, the audit-fix internal state tracks:

```json
{
  "finding_id": "3.2",
  "status": "fixed" | "deferred" | "reverted" | "pre_existing_failure",
  "attempts": [
    {
      "attempt": 1,
      "approach": "redact request body in logger.error",
      "result": "test failure: refresh_token_logs_no_secrets",
      "reverted": true
    },
    {
      "attempt": 2,
      "approach": "redact via err.into_response().redacted_for_log()",
      "result": "pass",
      "committed_as": "abc1234"
    }
  ]
}
```

This state is persisted in `.audit/audit-fix-state.json` so a paused or restarted session can resume coherently.

---

## When verification time becomes a problem

For very large codebases, full pre-commit can take minutes. If pre-commit is slow:

**Tier-aware fast checks:** for Tier 0 fixes (pure local), maybe only run the test file that exercises the touched function plus typecheck (skipping full build and integration tests). For Tier 2/3 fixes, run full pre-commit.

**Note:** this optimization is **off by default**. It introduces risk (the fast path can miss issues). Enable only when the user explicitly opts in: "Run audit-fix with fast-check on Tier 0 fixes."

Even with fast-check, the Phase 4 re-audit at the end runs full pre-commit and full audit — this is the safety net for any issues the fast path missed.

---

## When to skip verification (never, except this one case)

The skill should never skip verification *during* the fix loop. The only exception is when **pre-commit is the thing being fixed**:

> "Fix for finding 12 is updating `.pre-commit-config.yaml` itself. Pre-commit will run after the fix using the new config. If the new config is broken, we'll catch that in the next fix's verification (or at Phase 4 re-audit). Proceed?"

Even then, the skill should run a syntax check on the new config file before applying the fix.

---

## Communication discipline

When reporting verification failures:

- **Quote the actual error.** Don't paraphrase compiler/test output — paste it. The user needs the exact error to decide what to do.
- **Name the finding.** "Fix for finding 6.2 (auth/refresh.ts:88)" — not "the OAuth fix."
- **List options clearly.** Numbered, not paragraph form.
- **Don't suggest "try harder."** If a fix failed, suggesting a different approach is fine; suggesting "let me retry the same approach" is rarely useful.

The goal is to make user decisions about failures as fast as possible. A clear failure report → quick decision → fast resumption.
