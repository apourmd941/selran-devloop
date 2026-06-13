# Adversarial Verification (Steps 2.3b / 2.3c)

How to verify a fix without trusting the fixer. Two protocols: independent refutation for static-review findings, and red-green proof for test oracles.

## Why self-review fails

The model that wrote a fix verifies it with the same understanding that produced it. If that understanding missed an instance, misread the invariant, or confused "renamed the symptom" with "removed the cause," the self-review inherits the blind spot. This is not a hypothetical — "the AI confirmed its own fix and the bug remained" is one of the two highest-frequency residual-error sources in AI-assisted development (the other is vacuous tests).

The countermeasure is the same one human teams use: review by someone who didn't write the change, with access to the *requirement* rather than the author's *intent*.

---

## Protocol A — Independent refutation (static-review findings)

### With subagents (preferred)

Spawn a verification agent whose context contains ONLY:

1. The original finding text from AUDIT_LOG.md (severity, location, description, evidence) — exactly as the audit wrote it
2. The current file(s) at the cited location, plus anything the finding's evidence references
3. This instruction frame:

> "An audit recorded the finding below. The code may or may not have been fixed since. Your job is to determine whether the described issue is PRESENT in the current code. Actively look for it: at the cited location, elsewhere in the same file, and as the same pattern in sibling code. Do not assume it was fixed; do not assume it wasn't. Report: PRESENT (with location and evidence), ABSENT (with what you checked), or VARIANT (the literal issue is gone but the underlying problem survives in a changed form — describe it)."

**What the verifier must NOT see:** the fix diff, the fixer's reasoning, the commit message, or any "this was just fixed" framing. Contamination defeats the purpose — a verifier told "confirm the fix" confirms the fix.

**Verdict handling:**
- `ABSENT` → finding is fixed; record `re-verified: adversarial (independent) — no refutation`
- `PRESENT` → fix didn't land or was cosmetic → treat as "target check still failing" (Step 2.3): revert or extend, count a failed attempt
- `VARIANT` → the most valuable verdict: the fix moved the problem. Treat as PRESENT, and update the finding's description with the variant before re-fixing.

### Without subagents — structured self-refutation

Weaker than independence, far stronger than nothing. After a context break (finish the edit, run pre-commit, THEN do this — don't refute in the same breath as writing the fix):

1. **Re-derive from the description.** Read the original finding text. Without looking at your diff, predict what the code must now look like for the issue to be gone. Then read the code and compare against the prediction — not against your memory of the edit.
2. **Walk the four escape routes** (how wrong fixes survive review):
   - **Other instances**: the finding cited line 88, the fix fixed line 88 — does the same pattern exist at lines the audit didn't enumerate? Grep for the pattern, not the line.
   - **Cosmetic fix**: renamed/refactored so the *description* no longer matches but the *behavior* is unchanged (e.g., the token still reaches the log through a different call).
   - **Narrower than the finding**: the finding says "credentials never logged"; the fix handled one credential type on one path.
   - **Adjacent invariant broken**: the fix satisfies the finding but violates a neighboring requirement (added the transaction, but now holds it across an await; redacted the log, but swallowed the error).
3. Record honestly: `re-verified: self-refutation pass` — never label a self-pass as independent.

---

## Protocol B — Red-green proof for test oracles (Step 2.3c)

### When it applies

- The fix added a new test or modified an existing one
- A finding is being closed with "covered by test X" as the evidence
- pre-commit-verification wrote a new harness/regression test during this pass

### Mechanics

The goal: run the new test against the *buggy* code and watch it fail.

```bash
# Identify the fix's non-test files (the production-code side of the change)
PROD_FILES=$(git diff --name-only HEAD~1 | grep -v -E 'test|spec|__tests__')   # adjust to repo layout

# 1. Reverse-apply ONLY the production side, keeping the new test in place
git diff HEAD~1 -- $PROD_FILES | git apply -R

# 2. Run the specific test — EXPECT FAILURE
<run the one test>   # e.g. cargo test test_name / pytest path::test / npx vitest run -t "name"

# 3. Restore the fix
git diff HEAD~1 -- $PROD_FILES | git apply

# 4. Run the test again — expect PASS (confirms clean restore)
```

If the fix was committed in one commit (the default — one commit per fix), `HEAD~1` is the pre-fix state. For uncommitted fixes, use `git stash push -- $PROD_FILES` / `git stash pop` instead of reverse-apply.

**Safety:** steps 1–4 must complete as a unit. Verify the working tree is clean (`git status`) after step 4 — never leave the reverse-applied state behind. If anything goes wrong mid-protocol, `git status` + `git diff` against the fix commit is the recovery map.

### Verdict handling

- Test **fails** with bug present, **passes** with fix → real oracle. Record `test-oracle proven: red-green verified`.
- Test **passes** with bug present → **vacuous test.** The finding is NOT fixed regardless of what else is green. Diagnose which failure mode applies — asserts too little, mocks away the behavior under test, tests implementation detail rather than the finding's behavior, or wrong setup so the code path never executes — fix the test, and redo the proof.
- Test **fails to run** in the reverted state (compile error because it references a symbol the fix introduced) → weaker but acceptable evidence IF the compile failure is *because the behavior is absent*, not incidental. Prefer rewriting the test to target behavior over accepting this.

### Cost discipline

Red-green is cheap (two targeted test runs + two patch applications). Do it for **every** test that serves as a finding's oracle. The expensive variant — mutation-testing whole suites — is out of scope; this protocol only proves the tests that justify closing findings.

---

## What gets recorded

Every finding closed in Phase 2 carries its verification provenance in AUDIT_LOG.md:

```
- [High] workers/sync.rs:88 — race on status transition — fixed
  (audit-fix <version>, commit abc1234, re-verified: adversarial (independent) — no refutation,
   test-oracle proven: red-green verified)
```

Phase 4's re-audit treats `re-verified: self-refutation pass` on Critical findings as a flag: re-check those first.
