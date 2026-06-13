# Spec surface — claim-level drift, traceability, impact analysis

The mechanics behind app-audit Step 0.5.3's claim-level drift check and Step
5.6's traceability matrix, plus the impact-analysis query cartographer answers.
The shared idea: the spec is a set of **checkable claims wired to code
locations** (spec_refs), so divergence is detectable mechanically and coverage
gaps are visible as empty cells, not vibes.

## §1 — Claim-level drift detection (diff-driven)

Spec drift has two failure directions, and both are findings:

| Direction | Meaning | Grading |
|---|---|---|
| Code regressed | code changed, spec claim was right | normal Category 7 finding at normal severity |
| Spec stale | code changed *deliberately*, spec still claims old behavior | spec-drift finding (Medium default), phrased as a question |

Procedure (cost scales with the diff, not the spec):

1. **Anchor**: last round's closing SHA from `.audit/status.json`
   (`history[-1]` / the AUDIT_LOG entry). No prior round → skip; the full
   review covers the ground.
2. **Changed files**: `git diff --name-only <anchor>..HEAD`, minus
   generated/vendored paths (codemap tags).
3. **Invert spec_refs**: from `functions.json`, collect the spec sections
   cited by each changed file's functions. (Capability check applies — if the
   codemap was built without spec_refs, compute inline or skip with a note,
   per Step 0.5.3b.)
4. **Re-verify each cited claim** against the current code. Use the spec's
   provenance markers: `[confirmed]` disagreement → finding at the table
   above; `[observed]` → finding with the observed-baseline caveat;
   `[assumed]` → question, never a finding.
5. **Disagreement direction is a judgment call** — make it explicitly. A
   commit message like "speed up sync interval" suggests deliberate change
   (spec stale); no signal suggests regression. When unsure, write the finding
   as the question it is: "spec says X, code now does Y (since <commit>) —
   which is intended?" Never silently update the spec yourself: spec edits are
   the user's (spec-bootstrap hard rule 5).
6. **Uncovered changes**: changed files with no spec_refs at all get one
   aggregate note in the round report — they're spec-coverage gaps, not
   findings.

Drift findings land in AUDIT_LOG like any other; a "spec stale" resolution is
a spec edit (user) + cartographer re-tag, not a code fix — note that for
audit-fix so it doesn't try to "fix" code to match a stale claim the user just
disowned.

## §2 — Traceability matrix (`.audit/traceability.md`)

One row per spec section; every column comes from data the loop already
maintains — the matrix is assembly, not new analysis:

```markdown
# Traceability — SPEC v3 ↔ code ↔ tests ↔ findings (round 5)
<!-- regenerated each round by app-audit Step 5.6; a view, never a store -->

| Spec § | Provenance | Code (spec_refs) | Tests (acceptance map) | Findings (open/total) | Gap |
|---|---|---|---|---|---|
| §3.1 auth | confirmed | auth/refresh.ts, auth/oauth.rs | test_refresh_rotation | 0/3 | — |
| §3.2 deletion | confirmed | api/accounts.rs | — | 1/1 | NO TEST (UNMAPPED) |
| §4.2 sync interval | observed | workers/sync.rs | test_sync_cursor | 1/2 | DRIFT (round 5) |
| §5.1 export | confirmed | — | — | 0/0 | NO CODE REF |
| §7 rate limiting | assumed | — | — | — | UNCONFIRMED |

## Gaps ranked
1. §5.1 NO CODE REF — unimplemented, or implemented without spec_refs (check
   api/export.rs candidates by name).
2. §3.2 NO TEST — UNMAPPED acceptance row; Gherkin scenario exists, so the
   missing test's assertions are already specified.
3. §4.2 DRIFT — open spec-drift finding 5.3 (interval 5min vs 30s).
```

Gap semantics (the matrix's whole point):

- **NO CODE REF** — section claims behavior nothing implements (gap) or the
  implementation isn't tagged (tooling gap). Distinguish honestly: grep for
  obvious candidates before declaring it unimplemented, and say which case it
  is.
- **NO TEST** — exactly the acceptance map's UNMAPPED, surfaced per-section;
  Category 9 grades it (High for data-loss/security/privacy promises).
- **Findings concentration** — 3+ findings against one section across rounds
  = a section-level hotspot; feed it to Step 2.1's hotspot list next round.
- **UNCONFIRMED** — `[assumed]` rows aren't gaps, they're open questions;
  count them in the summary line so the interview backlog stays visible.

PRD-level tracing: when the repo has upstream product docs (PRD, issues) that
the spec cites, add a `Source` column carrying those links — but never
fabricate the linkage; if the spec doesn't cite sources, the column is absent,
not guessed.

## §3 — Impact analysis (cartographer query)

"What's impacted if I change X?" is a graph query over data cartographer
already holds — see cartographer SKILL.md "Impact analysis queries" for the
invocation; the contract:

- **Forward (who depends on X)**: BFS over `called_by` (functions) and
  `imported_by` (files), depth-limited (default 2 — beyond that, everything
  touches everything), annotated per level. This is audit-fix's blast-radius
  tiering, exposed as a question anyone can ask.
- **Backward (what X depends on)**: BFS over `calls` / `imports` — the answer
  to "what must hold for X to be correct".
- **Spec join**: each impacted function's spec_refs come along — so the answer
  isn't just "12 files" but "12 files implementing §3.1 auth and §4.2 sync",
  which is what makes impact reviewable against intent.
- Honesty rule carries over from cartographer's limits: static call graphs
  miss dynamic dispatch and reflection — say so in every impact answer rather
  than presenting the BFS as complete truth.

Audit uses: Phase 2 scope sizing ("changing the event bus touches 14 files —
audit those categories now or defer the refactor"), Step 2.4's blast-radius
expansion for PR scopes, and audit-fix Phase 1 tiering — all the same query at
different depths.
