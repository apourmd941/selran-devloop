# Fix Ordering

How audit-fix decides which finding to address first. The goal is to minimize regression risk during a multi-fix pass.

The intuition: a fix that only touches one function with zero callers is intrinsically safer than a fix that ripples across 15 files. By ordering fixes from "safest to apply" to "highest blast radius," any cascading failures show up earlier in the pass — when the recovery cost is lowest — and not after 10 successful-looking fixes have masked their cause.

---

## The five tiers

Every finding gets classified into one of five tiers based on cartographer's call-graph and dependency data.

### Tier 0 — Pure local

**Definition:** the function being fixed has empty `called_by` (nothing else in the codebase calls it), and the file it lives in has empty or test-only `imported_by`.

**Examples:**
- A private helper function with no external usage
- A bug in a top-level entry point (e.g., `main.rs` — nothing imports `main.rs`)
- A standalone utility script

**Why these go first:** the maximum cost of a wrong fix is breakage in the file itself, caught immediately by pre-commit. No cascading.

**Risk floor:** non-zero (a wrong fix can still break this file's tests), but bounded.

### Tier 1 — Same-file only

**Definition:** the function's `called_by` are all in the same file as the function. No cross-file dependencies on this specific function.

**Examples:**
- A helper used only by sibling functions in the same module
- A class method called only from other methods of the same class
- A worker's internal coordination function

**Why these come second:** fix scope is contained to one file. If pre-commit fails, the diff is small and localized.

**Risk floor:** slightly higher than Tier 0 — wrong fix can cascade through internal callers, but only within one file.

### Tier 2 — Bounded cross-file

**Definition:** the function's `called_by` span 2–4 files (across the codebase, not test files).

**Examples:**
- A service function called from two routes and one worker
- A schema validation function used by three different model layers
- A common error-handling utility used in several modules

**Why these come third:** real cross-file blast radius, but small enough to reason about. Pre-commit failure here is informative — usually one of the callers needs updating, easy to identify from the diff.

**Risk floor:** moderate. Cross-file refactor where callers may need coordinated updates.

### Tier 3 — Large blast radius

**Definition:** the function's `called_by` span 5+ files, or the file's `imported_by` span 5+ files.

**Examples:**
- Core type definitions used throughout the codebase
- Event bus / dispatcher functions
- A logging utility used in dozens of places
- A schema model imported by all data-access code

**Why these come last:** these are the high-risk fixes. A wrong fix here cascades widely; pre-commit failure can be hard to diagnose because the chain of dependents is long.

**When approaching a Tier 3 fix:** the skill should warn the user before applying:
> "Finding 13 (`core/event_bus.rs:55`) has Tier 3 blast radius — 14 dependent files. The fix may need coordinated updates across the dependent set. Recommended approach: I'll attempt the fix, then if pre-commit fails I'll surface the specific callers that need follow-up. Proceed?"

**Risk floor:** high. Per-fix verification is critical; revert behavior must be reliable.

### Tier 4 — File removal / disposition

**Definition:** the finding is on a file marked as `stale_candidate` in cartographer's `warnings.json.canonical_designations`. The fix isn't a code patch — it's removing or archiving the file.

**Examples:**
- `archive/old_auth.rs` (kept around, no longer used)
- `frontend/components/Dashboard.old.tsx` (suspicious-named backup)
- The non-canonical copy of `selran-app.json` (per Selran's canonical_designations)

**Why these are their own tier:** they don't have a "fix" in the patch-the-code sense. The action is: remove the file, or rename, or move outside the source tree.

**Special handling:** audit-fix never auto-removes files. It surfaces the disposition decision to the user:
> "Finding 14 is on a stale-candidate file (`archive/old_auth.rs`). The recommended action is removal, not patching. Options:
> - Remove the file (`git rm archive/old_auth.rs`)
> - Move to a non-source location (`git mv archive/old_auth.rs docs/archive/old_auth.rs.txt`)
> - Confirm it's intentional and add a comment explaining (skip)"

**Risk floor:** low for code, but high for user decision — file removal is irreversible from the audit's perspective even if `git` can undo it.

---

## Within-tier ordering

Within each tier, sort by severity descending:

1. Critical
2. High
3. Medium
4. Low
5. Info

Within the same severity, sort by file path alphabetically for determinism (so multiple runs produce the same order).

Why severity-within-tier rather than severity-across-tiers? Because severity tells you how bad the bug is *if it ships*, but tier tells you how likely the fix is to *introduce a new bug*. We're optimizing for safe progress, not for hitting the biggest fish first regardless of risk.

A Critical finding in Tier 3 still gets attention — it's just attended to after the Tier 0/1/2 critical findings have already cleared, when we have a known-good baseline.

---

## Edge cases and tiebreaks

### When call-graph data is missing

Cartographer may not have function-level `called_by` for files outside its tag profile (e.g., utility files not tagged `security-sensitive` / `auth` / etc.). In that case:

1. Fall back to file-level `imported_by` from `dependencies.json` to estimate blast radius
2. If even that's missing, default the finding to **Tier 2** (middle of the road — neither obviously safe nor obviously risky)
3. Note in the plan: "Tier estimated from file-level data; function-level call graph not available."

### When the same finding spans multiple tiers

Rare but possible — a finding cites a function whose own callers span different blast tiers. Use the **highest tier** any caller falls into. The fix's risk is bounded by its worst caller.

### When user disagrees with the tier

The plan in Phase 1 is shown to the user. If they say "actually fix #13 (Tier 3) first, I want to get it out of the way":

- Acknowledge the override
- Warn about the risk: "Tier 3 fix first means we don't have a clean baseline of small fixes when we hit any regression. I can do this, but be ready to revert."
- Proceed in user-specified order
- Per-fix verification still runs after each one

User authority overrides tier ordering. The skill's job is to advise, not to enforce.

### When all findings are Tier 3

Possible on a tightly-coupled codebase. Order by severity descending and proceed cautiously. Surface this in the plan:
> "All 8 findings are Tier 3 (large blast radius). Recommend doing this in 2-3 invocations rather than one — fix the 2 Critical findings, verify with re-audit, then come back for the rest."

### When findings have unresolved call data

In cartographer's call graph, some edges are marked `resolved: false` (the resolver couldn't pin down which function is called). When estimating blast radius:

- Count only resolved edges for "definite blast radius"
- Note the unresolved count for context: "5 definite callers, 8 possibly more (cartographer couldn't resolve)."
- Treat as Tier+1 (one tier higher) when unresolved count is large — assume the worst for safety

### When a finding cites a test file

Test files have their own propagation rules:

- A bug in a test file rarely cascades to production code
- But a bug in a test *helper* (called by many tests) cascades within the test suite

Treat test files as Tier 0 or Tier 1 depending on whether they're a test helper. If pre-commit's test run still passes after the fix, we're fine.

---

## Worked example — Selran mail app, hypothetical first audit

Suppose an audit on Selran produced these 8 findings:

| # | Severity | File:line | Issue |
|---|---|---|---|
| 1 | Critical | `backend-rs/src/services/oauth_refresh.rs:208` | Token leaked in error log |
| 2 | High | `backend-rs/migrations/...quarantine.sql:14` | Missing FK constraint |
| 3 | High | `backend-rs/src/routes/ws.rs:88` | Race in subscription cleanup |
| 4 | Medium | `frontend/src/components/InboxList.jsx:142` | Wrong sort order |
| 5 | Medium | `backend-rs/src/services/keychain.rs:55` | Error swallowed |
| 6 | Medium | `core/event_bus.rs:23` | No retry on emit failure |
| 7 | Low | `archive/old_auth.rs` | Stale-candidate file |
| 8 | Info | `backend-rs/src/utils/format.rs:12` | Inconsistent naming |

Cartographer's call graph shows:
- `oauth_refresh.rs::log_attempt` (cited by #1): called_by = 1 (same file)
- `ws.rs::cleanup_subscription` (cited by #3): called_by = 0 (just the route handler)
- `keychain.rs::load_token` (cited by #5): called_by = 4 across 3 files
- `event_bus.rs::emit` (cited by #6): called_by = 47 across 14 files
- `archive/old_auth.rs`: in canonical_designations as stale_candidate

Tier classification:
- **#1**: Tier 1 (same-file callers)
- **#2**: Tier 0 (schema file, no callers — pure local)
- **#3**: Tier 0 (called_by = 0)
- **#4**: Tier 1 (component, only same-file callers)
- **#5**: Tier 2 (callers in 3 files)
- **#6**: Tier 3 (47 callers in 14 files — large blast radius)
- **#7**: Tier 4 (file removal)
- **#8**: Tier 0 (utility, format.rs:12 is a constant)

Resulting order:

```
TIER 0 (pure local):
  #1 [Critical] oauth_refresh.rs:208 — token leaked in error log
  #2 [High]     quarantine.sql:14 — missing FK
  #3 [High]     ws.rs:88 — subscription cleanup race
  #8 [Info]     utils/format.rs:12 — naming

TIER 1 (same-file):
  #4 [Medium]   InboxList.jsx:142 — sort order

TIER 2 (bounded cross-file):
  #5 [Medium]   keychain.rs:55 — error swallowed

TIER 3 (large blast radius):
  #6 [Medium]   event_bus.rs:23 — retry on emit failure
                Warning: 47 callers; Tier 3 risk

TIER 4 (file disposition):
  #7 [Low]      archive/old_auth.rs — remove or move
```

Total: 8 findings. Critical/High concentrated in Tier 0/1 — the safe-to-fix-first zone. The trickiest (#6) lands at the end where any regression it causes shows up clearly against an otherwise-stable baseline.
