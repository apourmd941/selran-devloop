# Parallel specialized reviewers — dispatch & dedup

How Phase 3 runs the reviewer roster concurrently (Step 3.0b) and how Phase 4.5
runs the blind challenger (Step 4.5.3). The output is identical to a sequential
audit — the same findings list — just produced by focused agents in parallel.

## The roster

Read-only reviewer agents in `agents/` (no Edit/Write tools — they review, they
don't fix):

| Agent | Lens (categories) | Dispatch when |
|---|---|---|
| `gl-security-reviewer` | 3 | always |
| `gl-data-integrity-reviewer` | 1, 2 | DB / persistence / serialization present |
| `gl-concurrency-reviewer` | 5 | threads / async / workers / shared state present |
| `gl-reliability-reviewer` | 4, 6 | always |
| `gl-spec-compliance-reviewer` | 7 | `SPEC.md` exists |
| `gl-operational-reviewer` | 8, 10 | deployable service / app |
| `gl-test-coverage-reviewer` | 9 | always |
| `gl-challenger` | — | Phase 4.5 blind refutation |

## Conditional activation

Only dispatch a reviewer whose preconditions hold **and** whose categories are
in this round's scope. Decide from the Phase 0 stack detection + codemap tags:

- DB/ORM/migrations/serialization in the tree → `gl-data-integrity-reviewer`
- async / threads / worker pools / locks → `gl-concurrency-reviewer`
- a server/daemon/app entrypoint (not a pure library) → `gl-operational-reviewer`
- a `SPEC.md` → `gl-spec-compliance-reviewer`

A pure CLI with no storage shouldn't pay for a data-integrity pass; a library
with no service shouldn't get an operational pass. Skipping an inapplicable
reviewer is correct, not a coverage gap — note it in the coverage declaration.

## Dispatch (Phase 3)

Launch the selected reviewers in **one batch** (parallel Task calls). Give each:

- the scoped categories for this round,
- the change-set + base ref when the round is PR/diff-scoped (Step 2.4),
- the spec path (if any) and the `.codemap/` location,
- the instruction to emit findings only, in the standard format, and stop.

Then collect every reviewer's findings and merge:

1. **De-dupe.** Two lenses can flag the same `file:line` (e.g. a secret in a log
   is both Security and Diagnosability). Keep one instance — higher severity,
   then higher confidence — and merge the evidence/citations.
2. **Apply the global rules to the merged set:** stale-candidate downgrade
   (4.1.1), confidence (4.1.2), provenance (4.1.3).
3. Hand the merged set to Phase 4.5.

## Blind challenge (Phase 4.5)

For each Critical/High (and any <0.7) finding, dispatch `gl-challenger` with
**only** the finding's claim + severity + `file:line` and the surrounding code —
never the originating reasoning. It returns CONFIRMED / REFUTED / WEAKENED.
Challengers can run in parallel. Remove REFUTED findings (record as
considered-and-cleared); narrow WEAKENED ones; bump confidence on CONFIRMED.

## Cost / when to stay sequential

Parallel review spends more tokens (each reviewer reads independently). Worth it
for large codebases, many categories, or when wall-clock matters. For a small
repo or a tight PR diff, sequential is cheaper and just as good. When the host
can't spawn subagents at all, run sequential — the discipline (detectors →
grounded findings → challenge) is identical.
