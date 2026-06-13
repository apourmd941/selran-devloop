# Framework depth packs

Greenloop's base detectors and checklists are deliberately generic — they work
on any codebase. Packs add **framework-specific depth**: the bug classes that
only exist (or only matter) inside React, FastAPI, axum, etc. This is how
greenloop goes from "as good as the field" to *better on your actual stack*.

A pack is small and declarative — no code, no hooks:

```
packs/<name>/
  pack.yml        manifest: name, activates-on signals, contents
  rules/*.yml     semgrep rules (offline, same contract as the bundled ruleset)
  checklist.md    framework-specific checklist items, grouped by audit category
```

## The recall gate (a pack must prove itself)

**A pack ships only with benchmark fixtures demonstrating recall lift** — seeded
bugs in `benchmark/corpus/` that the pack's rules catch and the base bundled
ruleset does **not**, plus clean controls the pack must not flag. No proof, no
pack. This keeps packs from becoming opinion bundles: every rule earns its place
by catching a measurable class of bug at zero false positives on its controls.

Current packs and their proof fixtures:

| Pack | Activates on | Headline rules | Proof fixture |
|---|---|---|---|
| `react` | react in package.json deps | XSS via non-literal `dangerouslySetInnerHTML` | `react-dangerous-html` |
| `fastapi` | fastapi in Python deps | CORS wildcard + credentials (browsers reject it; devs then widen the hole), pickle on request data | `fastapi-cors-credentials` |
| `axum` | axum in Cargo.toml | `CorsLayer::permissive()` on an API router | `axum-cors-permissive` |

The axum rule has field provenance: greenloop's live shakedown (2026-06-12)
found exactly this — a new `CorsLayer::permissive()` on a loopback mail API,
confirmed High by blind challenge. The pack codifies that real finding so no
audited axum repo ships it again.

## Activation (automatic, declared, never silent)

app-audit Phase 0 detects the stack; any pack whose `activates_on` signals
match is **activated for the round**:

- Step 3.0 runs the pack's `rules/` with the other detectors
  (`semgrep --config packs/<name>/rules/ --json`); hits cite
  `pack:<name>/<rule-id>` and carry detector-grade evidence weight.
- Step 1.3 merges the pack's `checklist.md` items into the round's checklist,
  tagged `[pack:<name>]`.
- The coverage declaration names the active packs — and names matching packs
  that are NOT installed ("react detected; react pack not installed — framework
  depth not audited"), so absence is visible, same philosophy as
  `greenloop-doctor`.

Packs never widen scope on their own: their categories still obey the round's
Phase 2 scope, and quick-profile runs use pack *rules* (cheap, deterministic)
but skip pack *checklist* items (they belong to the standard pass).

## Authoring a new pack

1. `mkdir packs/<name>` + `pack.yml` (copy an existing manifest).
2. Write rules that are **high-signal and offline** — same bar as
   `references/detectors/greenloop.yml`: a hit should be worth a developer's
   attention nearly every time. Style nits belong in linters, not packs.
3. Write `checklist.md` items for what rules can't express (lifecycle, design,
   "verify X by reading Y") — grouped by the standard audit categories.
4. **Add the proof fixture(s)**: seeded bug + clean control + `ground-truth.json`
   in `benchmark/corpus/`, update `examples/run-good.json`, re-seed
   `benchmark/baseline.json`, and show base-ruleset-misses / pack-catches.
5. A pack rule that fires only false positives for two rounds follows the same
   retirement path as learned rules (`references/self-learning.md` §3).
