# Selran Greenloop

**The loop that runs until green.** By [Selran](https://github.com/apourmd941) —
written and maintained by **Aidin Eslampour**.

An autonomous, repeatable dev-loop for any codebase. Point it at a repo; it runs
**cartographer → app-audit → audit-fix** in a loop until the oracles are green —
no residual errors in the audited categories — then hands back reviewable commits.
Born from a simple frustration: AI-assisted builds where "done" was claimed but
errors always remained. Greenloop is the methodology that makes "done" checkable.

> Free for personal, non-commercial use. No redistribution or commercial use
> without permission — see [LICENSE](LICENSE).

**New here? [QUICKSTART.md](QUICKSTART.md)** — install to first findings in 60
seconds: say **"quick audit"** for a zero-setup, minutes-long pass; plain
**"audit"** for the standard loop; **"deep audit"** for everything.

(The engine's internal name remains `devloop` — config dir `.devloop/`, driver
`devloop.py`, CLI `autoloop`. Greenloop is the product; devloop is the plumbing.)

## What this is (and isn't)

- **Is:** the engine that drives the five skills to convergence, in a sandbox, on
  an isolated branch, with budget caps and a human review gate.
- **Is not:** any one app. DevLoop operates *on* your repos (your-rust-app,
  your-other-app, your-python-app, …); they don't live here. Each target repo just gets a
  `.devloop/autoloop.toml`.

## The five skills (source of truth lives here)

`skills/` is now the canonical home for the methodology skills — replacing the old
LocalDrop copies. A tagged DevLoop release pins a known-good combination of all
five, which is what kills the version drift we used to hit.

| Skill | Version | Role |
|---|---|---|
| cartographer | 0.6.0 | Maps the codebase (`.codemap/*.json`); answers impact-analysis queries ("what's impacted if I change X?") over the call graph with spec sections joined in |
| pre-commit-verification | 0.9.0 | Runs tests, acceptance map + the smoke/integration harness (incl. browser verification for web UIs); tamper-proof clean-room re-runs in a fresh worktree; optional Ed25519-signed witness manifest; per-check reliability (pass³) tracking that exposes flaky checks |
| spec-bootstrap | 0.2.0 | Reconstructs a provenance-marked design spec for apps that never had one; optional EARS requirements + Gherkin scenarios (seeding the acceptance map), ADRs, and a C4-style diagram derived from the codemap |
| app-audit | 0.14.0 | Convergent audit (10 categories) — deterministic detectors → grounded findings with confidence + new/pre-existing provenance → adversarial challenge; whole-codebase **or** PR/diff-scoped with findings posted as PR comments / issues; read-only-enforced review window; self-learning (chronicle, cleared registry, learned detector rules, opt-in shared brain); resumable rounds, churn×coverage hotspots, TECHNICAL_DEBT.md + status.json + optional HTML dashboard; opt-in cross-provider second opinions (codex/gemini/ollama) with consent gate; claim-level spec-drift detection + per-round traceability matrix; detector-readiness probe + bundled offline SAST ruleset; SARIF / code-scanning export + GitHub/GitLab CI templates with a merge gate; governed suppressions (.greenloopignore + inline, reasons mandatory, expiry-dated, meta-audited); framework depth packs (react/fastapi/axum, recall-gated); live panel via Selran Hub when present |
| audit-fix | 0.14.0 | Fixes findings safely (baseline-aware verify, adversarial re-verification — optionally by a different provider, 0–1 truth-score gate per fix, blind-authored proof-tests, blast-radius + provenance ordering, worktree-isolated PR fixes, Conventional Commits, clean-room close, chronicle fix-lessons, crash-safe resume, live fix progress via Hub) |

### What's new (v1.17.0)

The audit dashboard became a **findings workbench.** Run through
design-director (technical-minimal — one forest-green accent, a five-step
severity ramp, monospace data, system-sans chrome, zero webfonts), it now
carries: **search + severity-chip filters**, a **drill-in drawer** (click any
finding for its description, evidence, code snippet, suggested fix, and
suppression reason), and a fifth **Suppressed** column so accepted findings stay
visible instead of vanishing. The local run UI (`ui/devloop_ui.py`) was
rethemed to the same system (dropped Inter, added the green identity and a dark
mode). Still one self-contained file — no server, no CDN, no network — and a
pure view of `.audit/status.json`. Design system: [ui/design-system.md](ui/design-system.md).

### What's new (v1.16.0)

Greenloop now goes **deeper on your actual stack.** Framework packs
(`packs/` — react, fastapi, axum) add the bug classes that only exist inside a
framework: non-literal `dangerouslySetInnerHTML` (XSS), CORS
wildcard-with-credentials, `CorsLayer::permissive()` on an API router — that
last one codified from a **real shakedown finding** (blind-challenge-confirmed
High). Packs auto-activate on stack detection, run their semgrep rules with the
detectors, merge checklist items into the round, and are named in the coverage
declaration (including "detected but not installed" — absence is visible). The
discipline: **a pack ships only with benchmark fixtures proving recall lift** —
its rules must catch seeded bugs the base ruleset misses, at zero false
positives on clean controls. All three packs pass that gate (base 0/3 → packs
3/3, 0 FPs); the benchmark corpus grew to 7 fixtures. See
[packs/README.md](packs/README.md).

### What's new (v1.15.0)

Greenloop now **meets you at your level.** Three audit profiles: **quick**
("quick audit" / "sanity check" — detector-grounded, hotspots-first, zero
setup, minutes), **standard** (plain "audit" — the full loop), and **deep**
("deep audit" / "release audit" — parallel reviewers, cross-provider
challenge, clean-room, every artifact). Profiles change *how much* runs,
never *how well* — severity rules, confidence scoring, and honest coverage
declarations are identical in all three, and a quick audit **ends by declaring
what it skipped** ("smoke detector, not a clearance"). New
[QUICKSTART.md](QUICKSTART.md): install → first findings in 60 seconds.

### What's new (v1.14.0)

Teams can now say **"we accept this" without ignore-file rot.** A
`.greenloopignore` (path/rule globs) and inline `greenloop:ignore[<rule>]`
markers suppress findings durably — but **governed**: every suppression needs a
reason, Critical findings require an expiry date (paused, never buried),
expired suppressions stop suppressing, and the suppression set is itself
**meta-audited every round** (expired / invalid / stale / over-broad entries
get flagged). Suppressed findings are never deleted — they keep their own
buckets in `status.json` (so the CI merge gate honors team decisions with zero
extra logic) and export as SARIF suppression objects ("dismissed with reason")
instead of vanishing. Engine: `scripts/greenloop-suppress.py` (stdlib-only) —
see [suppressions.md](skills/app-audit/references/suppressions.md).

### What's new (v1.13.0)

Greenloop findings now land **where developers already look.** A converter
(`scripts/greenloop-sarif.py`) turns a round's `status.json` into **SARIF
2.1.0** — the standard format GitHub code-scanning renders inline on PRs and in
the Security tab, and the VS Code SARIF viewer shows in the Problems panel —
plus **GitLab Code Quality** JSON for inline MR rendering. Ready-to-copy
pipelines ([GitHub](ci/github/greenloop-audit.yml), [GitLab](ci/gitlab/greenloop-ci.yml))
run the audit, upload the SARIF, and **gate the merge** on open Critical/High
with a single `jq` line against `status.json`. SARIF `partialFingerprints` make
the platform de-dupe alerts across re-runs even when lines shift. No greenloop
UI required — see [ci-sarif.md](skills/app-audit/references/ci-sarif.md).

### What's new (v1.12.0)

Greenloop now **guarantees its detector grounding is present or known-absent.**
A `greenloop-doctor` probe (`scripts/greenloop-doctor.sh`, also `./install.sh
--doctor`) reports which detector tiers are live — SAST / dependency-CVEs /
secrets / type-checkers — and the exact command to install what's missing, so a
missing analyzer can no longer *silently* degrade findings to judgement-only
(the gap a live shakedown exposed). It's honest per-tier: it won't claim
`npm-audit` covers a Rust repo with no `package.json`. And because
`semgrep --config auto` needs the network, greenloop ships a curated **offline
SAST ruleset** (`skills/app-audit/references/detectors/greenloop.yml`) that runs
on a bare machine — validated against the benchmark to catch the seeded SQL
injection and secret-in-log with zero false positives on their clean controls.

### What's new (v1.11.0)

Greenloop now **measures its own quality**. A benchmark harness (`benchmark/`)
runs the audit against a corpus of fixtures with deliberately-seeded bugs and
clean controls, then scores **recall** (seeded bugs found), **precision /
false-positive rate** (clean code wrongly flagged), and **severity accuracy** —
with a committed baseline and a **regression gate** so a skill edit that lowers
quality fails before it merges. This is the answer to the field's real remaining
lead (maturity, not capability): you can't prove "unproven," but you can measure
it and protect what you measure. Stdlib-only scorer, no dependencies — see
[benchmark/README.md](benchmark/README.md).

### What's new (v1.10.0)

Greenloop grew nine capability layers, closing the gaps that separated it from
the strongest review/audit plugins:

- **Spec surface (G9).** The spec becomes a set of **checkable claims wired to
  code**. Diff-driven **claim-level drift detection** catches the silent kind
  of rot — code changed, spec still claims the old behavior — and reports the
  disagreement as the question it is (regression, or stale spec?). Each round
  emits a **traceability matrix** (spec § ↔ implementing code ↔ asserting test
  ↔ findings) whose gap columns are the product: unimplemented sections,
  untested promises, finding hotspots. spec-bootstrap can formalize
  high-stakes statements as **EARS requirements** and user-facing musts as
  **Gherkin scenarios** (which pre-seed the acceptance map), record decisions
  as **ADRs**, and derive a **C4-style Mermaid diagram** from the codemap.
  cartographer now answers **impact analysis** directly: "what's impacted if I
  change X?" → forward/backward BFS with spec sections joined in, honestly
  labeled as a lower bound.
- **Multi-model & adapters (G8).** Opt-in **cross-provider review**: when a
  second-model CLI is present (Codex, Gemini, or **Ollama for fully-local**
  inference), Critical/High findings face a **cross-model blind challenge**
  and PR diffs can get an independent second opinion — different model
  family, different blind spots. Hard rules: explicit **consent before any
  code leaves the machine**, external verdicts adjust confidence but **never
  auto-remove** a grounded finding, local models carry half weight, and a
  failing CLI never blocks the audit. Ask for a "multi-model review" to turn
  it into a **consensus gate**. The five skills also now travel:
  `scripts/export-agent-skills.sh` bundles them as an AGENTS.md file (OpenCode,
  Cursor, …) or copies them to any skills directory — see
  [docs/ADAPTERS.md](docs/ADAPTERS.md) for what's portable vs.
  Claude Code-only.
- **Workflow & reporting (G7).** Audits are now **crash-safe and
  machine-readable**. An interrupted round resumes from its on-disk checkpoint
  ("resume the audit") — scope, cursor, and findings survive session death;
  audit-fix recovers the same way from its plan + per-fix commits. Scope
  proposals rank files by **churn × coverage hotspots** so review depth lands
  on the riskiest files first. Each round refreshes **`TECHNICAL_DEBT.md`**
  (the accepted-debt ledger, with age flags), **`.audit/status.json`** (a
  versioned schema with a per-round timeline — CI can gate on
  `jq '.findings.open.critical == 0'`), an optional **self-contained HTML
  dashboard** (Kanban board, trends, no server/CDN), and honest **run metrics**.
  pre-commit-verification tracks per-check reliability across runs (**pass³**)
  and surfaces flaky checks instead of retrying them green.
- **Self-learning (G6).** The audit now **gets smarter about your repo every
  round**. Findings that recur 3+ times are codified — as `[learned]`
  checklist items and as **learned detector rules** (semgrep/grep) that run
  deterministically from the next round on. A per-repo **chronicle** carries
  lessons forward (env gotchas, user-confirmed intentional oddities, fix
  approaches that failed) and keeps a **cleared registry** so a finding refuted
  once is never re-litigated on unchanged code. Project-agnostic lessons can
  optionally distill — **privacy-scrubbed, with your approval** — into a
  cross-project brain (`~/.greenloop/brain.md`).
- **Verification depth (G5).** "Fixed" is now a graded, tamper-evident claim,
  not a feeling. Every fix gets a **0–1 truth score** from explicit evidence
  signals (oracle passed, no regressions, adversarial re-verification,
  red-green proof, minimal diff), gated by destination — **dev 0.90 / PR 0.95 /
  release 0.99** — with strengthen-or-rollback below threshold. Proof-tests are
  **authored blind** (from the finding + spec, never the fix diff) and frozen.
  Each pass closes with a **clean-room re-run** in a fresh worktree of HEAD, so
  uncommitted state can't rig a green verdict, and can emit an
  **Ed25519-signed witness manifest** (`ssh-keygen -Y`) making "it was green at
  commit X" checkable. Browser-driven verification (Playwright against the real
  rendered page) is required when a change touches web UI.
- **Parallel specialized reviewers (G4).** For large codebases, the audit can
  dispatch a roster of **read-only reviewer subagents concurrently** — security,
  data-integrity, concurrency, reliability, spec-compliance, operational,
  test-coverage — each owning one lens, with **conditional activation** (no
  data-integrity pass on a storage-less CLI). Findings are de-duped and merged,
  then a blind **challenger** subagent refutes each one (it never sees the
  reasoning that produced it). Sequential mode remains the default for small
  repos. See [parallel-review.md](skills/app-audit/references/parallel-review.md).
- **Hooks + enforcement (G3).** Greenloop is now a full plugin, not just
  skills. A PreToolUse guard makes the auditor **physically read-only during a
  review** — it can't silently "fix as it goes," which is what keeps findings
  objective (the eight-eyes / mumei discipline). A SessionStart hook warns when
  the codemap is stale or findings are open; an opt-in PostToolUse hook
  auto-formats edited files. The guard is inert outside audits, crash-safe, and
  has a `GREENLOOP_BYPASS=1` escape hatch — see [docs/HOOKS.md](docs/HOOKS.md).


- **Finding quality (G1).** The audit now runs real analyzers first
  (osv-scanner / semgrep / gitleaks / type-checkers) and *adjudicates* their
  output; every finding carries a 0–1 **confidence** and **new vs. pre-existing**
  provenance (via git blame); and a final **adversarial challenge** pass tries to
  *refute* each Critical/High finding, removing the ones that don't survive.
  Net effect: far fewer false positives — the #1 complaint about audit tools.
- **PR / VCS integration (G2).** Point the audit at a **PR, branch, or diff**
  (`review my PR`, `review the last 3 commits`, a PR URL); it scopes to the
  change-set + blast-radius, leads with regressions, and can **post findings as
  inline PR comments and GitHub/GitLab issues** or run in **CI**. Fixes can be
  isolated in a git worktree and land as Conventional Commits.

The nine-layer competitive-gap roadmap (G1–G9) is complete. Future work is
driven by field feedback — [open an issue](https://github.com/apourmd941/selran-devloop/issues).

## Installing

### As a Claude Code plugin (recommended for sharing)

This repo is a Claude plugin marketplace. Anyone can install Greenloop with two
commands inside Claude Code:

```
/plugin marketplace add apourmd941/selran-devloop
/plugin install greenloop@selran
```

That loads all five skills (namespaced as `greenloop:cartographer`, etc.) and
keeps them updatable via `/plugin marketplace update selran`.

### With the interactive installer (local copy)

One interactive installer explains each option and copies what you pick to
`~/.claude/skills/`:

```bash
./install.sh
```

It offers:

- **One skill at a time** — cartographer, pre-commit-verification,
  spec-bootstrap, app-audit, or audit-fix (with their dependencies pulled in
  automatically).
- **All five skills** (`./install.sh --all`) — the recommended methodology-only
  setup. Use the skills directly from Claude Code without the autonomous loop.
- **Full DevLoop engine** (`./install.sh --devloop`) — all five skills + the
  `autoloop` runner that drives cartographer → app-audit → audit-fix to
  convergence and opens a reviewable PR. Verifies Python / Agent SDK / `gh` /
  API key as part of the install.

`./install.sh --help` prints the same menu without installing anything, so a
new user can read what each piece does before choosing.

For Codex, install the same five skills into `~/.codex/skills/`:

```bash
scripts/install-codex-skills.sh
```

Restart Codex after installing so the skills appear in the automatic skill list.

For other agent CLIs (OpenCode, Cursor, anything that reads AGENTS.md or a
skills directory):

```bash
scripts/export-agent-skills.sh --agents-md     # one bundled GREENLOOP-AGENTS.md
scripts/export-agent-skills.sh --copy <dir>    # or copy skills verbatim
```

See [docs/ADAPTERS.md](docs/ADAPTERS.md) for per-host notes and what's
portable (the methodology) vs. Claude Code-only (hooks, subagents).

## Local progress UI

A tiny local dashboard can launch `autoloop` and show the workflow as:
`cartographer` stages 1-4, `pre-commit-verification`, `app-audit`,
`audit-fix`, and `loop`.

```bash
python3 ui/devloop_ui.py
```

It defaults to dry-run mode so the control flow can be tested without API calls,
commits, pushes, or PRs. Host and sandbox modes use the existing `autoloop`
prerequisites.

## Layout

```
QUICKSTART.md            install → first findings in 60 seconds
install.sh               friendly installer (interactive picker)
skills/                  the 5 methodology skills (source of truth)
benchmark/               self-evaluation harness (seeded-bug fixtures + scorer + regression gate)
packs/                   framework depth packs (react, fastapi, axum — rules + checklists, recall-gated)
scripts/greenloop-doctor.sh  detector-readiness probe (which analyzers are live; --install to add them)
scripts/greenloop-sarif.py   status.json → SARIF 2.1.0 / GitLab Code Quality (code-scanning export)
scripts/greenloop-suppress.py  governed suppressions (.greenloopignore + inline markers, expiry + meta-audit)
ci/                      ready-to-copy GitHub Actions + GitLab CI pipelines (audit → SARIF → merge gate)
ui/                      local progress dashboard for cartographer/audit/fix/loop runs
sandbox/                 the reproducible Linux container image (Phase 1)
driver/                  the Agent SDK loop driver (Phase 3)
cli/                     the `autoloop` CLI (Phase 4)
templates/               per-repo config template (autoloop.toml.example)
scripts/install-skills.sh  legacy "install all 5 skills" non-interactive helper
docs/DESIGN.md           the full build plan + architecture decisions
```

## Status

Build-out complete — `cartographer → pre-commit/harness → app-audit → audit-fix →
driver → autoloop`. All phases built and verified:

| Phase | What | State |
|---|---|---|
| 1 | Sandbox image + Linux boot gate | ✅ PASS (v4 backend builds + boots in the container) |
| 2 | Oracle layer (`make smoke`) | ✅ backend verified; frontend scaffolded (Tauri caveat) |
| 3 | Agent SDK loop driver | ✅ orchestration verified via `--dry-run` |
| 4 | `autoloop` run wrapper + PR gate | ✅ orchestration verified via `--dry-run` |
| 5 | Repeatability | ✅ proven on your-python-app (Python) — config-only |

The one outstanding item is the first **live** end-to-end run, gated on
`ANTHROPIC_API_KEY` in the sandbox + real API spend (the same kind of gate as
Phase 1's container runtime). See `sandbox/PHASE{1..5}-FINDINGS.md` and
`docs/ONBOARDING.md`.

## Hard rules (carried into every phase)

- Never run against `main` — always an isolated branch, always in the sandbox.
- Never put real secrets in the sandbox — throwaway/file-based keys only.
- Per-fix verification + revert-on-failure (audit-fix enforces this).
- Human review gate: the loop opens a PR; you merge. Nothing auto-touches main.

## Feedback & contributions

Bug reports and feature requests are very welcome — [open an issue](https://github.com/apourmd941/selran-devloop/issues).
Pull requests are not accepted: to keep authorship and licensing unambiguous, all
code in this repository is written by the author. If you've found a fix, describe
it in an issue and it will be credited in the changelog.

## Attribution & license

Selran Greenloop — © 2026 Selran. Created and written by **Aidin Eslampour**.

Free for **personal, non-commercial use**. Commercial use, redistribution outside
the official channels (this repository and marketplace entries pointing to it),
and rebranding require written permission — see [LICENSE](LICENSE). For commercial
licensing: aidin.eslampour@selran.ai.
