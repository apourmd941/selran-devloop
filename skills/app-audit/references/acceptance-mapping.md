# Acceptance Mapping (spec → test)

The mechanism behind Category 9's acceptance-map completeness check. The map makes "every user-facing promise has a test" a verifiable claim instead of an impression.

## The problem it solves

The smoke harness proves the app *launches and runs*. Unit tests prove functions compute. Neither proves that **features behave as promised**: the app can boot cleanly, pass every unit test, and still show the wrong data after the second click — and that class of error is what users actually hit. Without an explicit map, "the e2e suite covers the important stuff" is a feeling; with one, an unmapped promise is a visible, gradeable gap.

## The file: `.audit/acceptance-map.md`

One table, maintained alongside the checklist:

```markdown
# Acceptance map — spec v3 (regenerate on spec version change)
Generated: 2026-06-09 by app-audit Phase 1.3b. Status values: mapped | UNMAPPED | n/a (reason).

| Spec ref | Promise (short) | Test | Status |
|---|---|---|---|
| §3.1.2 | Deleting a project requires confirmation | e2e/projects.spec.ts :: "delete requires confirm" | mapped |
| §3.4.1 | Draft survives app restart | e2e/drafts.spec.ts :: "draft persists across relaunch" | mapped |
| §7.2   | Undo available for 5 minutes after send | — | UNMAPPED |
| §8.1   | Tokens never logged | — | n/a (not e2e-testable; covered by Cat 3 static + harness [1+4]) |
| §2.3   | Postgres only | — | n/a (architectural; Cat 7 static check) |
```

Rules:

- **Rows come from the spec, not from the tests.** Walk the spec's user-facing musts (Category 7's extraction already produces this list); each user-observable one gets a row. Mapping tests→spec instead would hide exactly the gaps the map exists to expose.
- **"User-facing" means observable by a user through a surface** (UI, API response, CLI output, file the user sees). Internal invariants stay in Categories 1–6.
- **`n/a` requires a reason**, and the reason must name where the promise IS verified (another category, a harness check, a static check). "Hard to test" is not an `n/a` reason — it's an UNMAPPED with a note.
- **The test column is precise**: file plus test name, so staleness is detectable mechanically.

## Lifecycle

**Generated** by app-audit Phase 1.3b (right after checklist generation): extract user-facing promises, then look for matching tests by grepping test names/descriptions for the feature's terms — propose matches, don't assume them. A proposed match must actually assert the promise; a test that merely *touches* the feature doesn't count.

**Verified** by Phase 3, Category 9:
1. Every user-facing must from the spec has a row (diff spec extraction vs map — missing rows are themselves findings: the map rotted)
2. Every `mapped` test exists, is not skipped, and asserts the promise
3. UNMAPPED rows become findings (High for data-loss/security/privacy promises, Medium otherwise)
4. Stale test references → Medium finding

**Consumed** by pre-commit-verification: when `.audit/acceptance-map.md` exists, the mapped tests are part of the verification surface, and the structured report includes `acceptance: N mapped, M run, K UNMAPPED`. Pre-commit runs the tests; only the audit grades the gaps.

**Regenerated** when the spec version changes (Phase 0.5.3 spec-drift detection triggers it). Old map is kept as `acceptance-map.<old-version>.md` for one cycle.

## Writing the missing tests

Closing an UNMAPPED gap is remediation, not audit work — it becomes a finding that audit-fix (or the user) addresses. When audit-fix writes an acceptance test to close one:

- The test asserts the **promise as stated in the spec**, in user-observable terms — not the implementation
- It runs in the launched/integrated context the promise lives in (e2e for UI promises, API-level for API promises)
- It is subject to Step 2.3c (red-green proof): break the behavior once, watch the test fail, restore. An acceptance test that can't fail is worse than no test — it turns the map into false confidence
