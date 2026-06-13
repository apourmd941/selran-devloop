# Regression Detection

In Phase 4, audit-fix re-runs app-audit on the full original scope. This generates a fresh AUDIT_LOG.md entry with the post-fix findings. The question this file answers: **of the findings in that fresh entry, which are new regressions caused by the fixes, and which are pre-existing issues we didn't address?**

Getting this right matters because:
- If we wrongly flag a pre-existing finding as a regression, we waste time investigating
- If we miss a real regression, we ship a bug introduced by the fix loop

---

## The three classes of post-fix findings

Every finding in the Phase 4 audit falls into one of three categories:

### Class 1 — Finding was in the original audit, status still `open`

The fix loop didn't address this finding (it was deferred, or the user chose to skip it). It re-appears in Phase 4 because audit found it again. **Not a regression.**

How to detect: compare each new finding against the original audit's findings list by (location, type). If location + type matches a still-open finding from before, it's a re-occurrence, not a regression.

Output:
```
Finding 9.3 [Medium] api/contacts.rs:45 — null handling
  Status: still open (was deferred during this audit-fix pass)
```

### Class 2 — Finding wasn't in the original audit, but pre-existed the fixes

The original audit missed it. Maybe the checklist was incomplete, maybe the audit didn't go deep enough on this category. Either way, the finding existed before audit-fix touched anything.

How to detect: check `git log --before <audit-start-commit>` for the cited file. If the relevant code existed at audit-start time and has the same shape, this is a pre-existing issue the audit missed.

Output:
```
Finding 9.4 [High] frontend/src/state.ts:88 — race condition
  Status: NEW finding, but pre-existed audit-fix (code unchanged since audit baseline)
  Recommend: include in next audit checklist; not introduced by fixes
```

### Class 3 — Finding caused by an audit-fix change

The finding's cited file was modified by audit-fix during Phase 2. The new finding's location corresponds to or is downstream of the modified code.

This is the **real regression class**. These are the bugs the fix loop introduced.

How to detect: cross-reference the new finding's file against the list of files audit-fix touched in Phase 2 (`.audit/audit-fix-state.json` tracks this). If the new finding's file or its `imported_by` chain includes a fix target, it's likely caused by the fixes.

Output:
```
⚠ Finding 9.5 [High] workers/sync.rs:88 — race condition
  Status: REGRESSION — likely caused by fix for finding 6 (oauth_refresh.rs)
  Reason: workers/sync.rs imports oauth_refresh; fix changed error flow that sync.rs depends on
```

---

## The detection algorithm, step by step

For each finding in the Phase 4 audit:

```
1. Look up (file, line-range, type) against the original audit findings.
   If match found and status was 'open' → Class 1, skip further checks.

2. Check audit-fix's Phase 2 state — was this file touched during fixes?
   If yes → likely Class 3, mark as 'regression-candidate', go to step 4.

3. Check if any of this file's dependencies (from cartographer's dependencies.json)
   were touched during fixes.
   If yes → possibly Class 3 via cascade, mark as 'cascade-candidate', go to step 4.

4. For candidates, do a deeper check:
   - Run `git log --follow <file>` to find the commit that introduced the affected lines
   - If commit is from the audit-fix pass → Class 3 (regression)
   - If commit predates audit-fix → Class 2 (pre-existing)
   - If commit is post-audit-fix but not from the fix run (e.g., user committed something
     in parallel) → Class 2, flag for user attention

5. If file wasn't touched and no dependencies were touched → Class 2 (pre-existing).
```

---

## Common cascade patterns to watch for

These are the regression patterns the algorithm should flag prominently:

### Pattern 1 — Signature change cascade

The fix changed a function's signature (parameter types, return type). Callers still compile (Rust's pattern matching or TypeScript's structural typing can mask the issue), but runtime behavior changes.

Detection: the fix file appears in the regression-candidate's import chain, and the fix touched a function in the relevant call-graph branch.

Risk level: **high**. Build passing doesn't mean behavior is preserved.

### Pattern 2 — Removed side effect

The fix simplified or removed something that another part of the system silently depended on. Examples:
- Removed a `logger.info()` that an external log monitor parsed
- Removed a cache invalidation that other code assumed
- Removed an event emission

Detection: search for the removed lines across the codebase. If any other file references the removed name (function call, log parsing pattern, event subscription), flag as cascade.

Risk level: **high**. These are the silent regressions that don't surface in tests.

### Pattern 3 — Concurrency reordering

The fix changed timing or ordering in async code. New race conditions can appear.

Detection: if the fix file is tagged `concurrency` or `async` and the regression-candidate is also in that category, flag for manual review even if no obvious chain.

Risk level: **moderate-to-high**. Often only detected at runtime under load.

### Pattern 4 — Schema-aware code drift

The fix touched a database access pattern. Other code that reads from the same table may now make wrong assumptions.

Detection: if the fix file is tagged `db` or `data-model`, check other files tagged `db` for any new findings.

Risk level: **moderate**. Usually surfaced by integration tests if they exist.

### Pattern 5 — Test coverage gap

The fix introduced new behavior that has no test. A future change to this code could regress without anyone noticing.

Detection: not really a regression per se, but the Phase 4 audit's Category 9 (test coverage) may flag the new code as untested.

Risk level: **moderate**. Not a current bug but a future one.

---

## How to present the Phase 4 results

A clean report:

```
=== Phase 4 — Re-audit complete ===

Findings comparison:
  - Original audit: 14 findings
  - Addressed by audit-fix: 12 (10 fixed, 2 deferred)
  - Re-audit findings: 5

Of the 5 re-audit findings:

CLASS 1 — Previously open, not addressed (2):
  • [Medium] event_bus.rs:23 — no retry on emit (deferred Tier 3)
  • [Low]    archive/old_auth.rs — stale candidate (deferred file disposition)

CLASS 2 — New, but pre-existed audit-fix (2):
  • [High]   frontend/state.ts:88 — race condition (audit-fix didn't touch state.ts;
             this was missed in the original audit)
  • [Low]    utils/parse.rs:55 — error swallowed (also pre-existing)

CLASS 3 — REGRESSION caused by fixes (1):
  ⚠ [High]  workers/sync.rs:88 — race condition
            Likely cause: fix for finding 6 (oauth_refresh.rs) changed error
            propagation; sync.rs expected the old error type.
            
Recommended next steps:
  - Address the regression in workers/sync.rs (Class 3) before considering this round closed
  - Class 1 deferred items remain on the docket
  - Class 2 new findings should be added to next round's scope
```

If there are zero Class 3 findings, that's the success signal:
> "Re-audit clean. No regressions introduced by this audit-fix pass."

---

## When detection is uncertain

The algorithm above uses heuristics. It will sometimes be wrong:

- A "Class 2" finding might actually be caused indirectly by audit-fix (through a non-obvious dependency)
- A "Class 3" finding might be coincidental — the user changed something in parallel that audit-fix flagged

When uncertain, **flag as `regression-candidate` and let the user decide**. Don't claim certainty the algorithm doesn't have.

The user can override:
```
> "Finding 9.5 isn't related to the fixes — I made an unrelated change in workers/sync.rs
>  yesterday that audit didn't catch."
```

In that case, reclassify as Class 2 and proceed.

---

## What to do with regression-candidates

Phase 4 surfaces them but doesn't auto-fix. The user has three options:

1. **Address now** — start a new audit-fix invocation scoped to the regressions
2. **Treat as next round** — let them sit; address in the next planned audit cycle
3. **Revert the causing fix** — if the regression is severe and the fix it caused isn't critical, undo the fix

The skill presents these options after the Class 3 findings list, doesn't make the choice.

---

## A note on detection limits

Static analysis can identify **likely** regressions. It can't identify all of them. Things this approach misses:

- **Data-state regressions** — fix works fine for the test data but breaks on production-shape data
- **External-API contract changes** — fix changes the response your API sends; downstream consumers break
- **Performance regressions** — fix is correct but slower; tests pass but production degrades
- **UI/UX regressions** — fix changes visible behavior; tests pass but users notice

These need human review of the fix diff, not algorithmic detection. The Phase 4 report should remind the user:

> "Phase 4 catches regressions visible to the audit checklist. Runtime, performance, data-state, and UX regressions need separate verification (manual review, staging deployment, etc.)."
