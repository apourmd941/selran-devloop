# Selran DevLoop

An autonomous, repeatable dev-loop for any of the Selran apps. Point it at a repo;
it runs **cartographer → app-audit → audit-fix** in a loop inside a disposable
Linux sandbox until the oracles are green, then hands back reviewable commits as a
pull request.

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
| cartographer | 0.5.0 | Maps the codebase (`.codemap/*.json`) |
| pre-commit-verification | 0.7.0 | Runs tests, acceptance map + the smoke/integration harness |
| spec-bootstrap | 0.1.0 | Reconstructs a provenance-marked design spec for apps that never had one |
| app-audit | 0.7.0 | Convergent audit (10 categories incl. acceptance mapping + diagnosability) |
| audit-fix | 0.7.0 | Fixes findings safely (baseline-aware verify, adversarial re-verification) |

## Installing — pick what you want

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
install.sh               friendly installer (interactive picker)
skills/                  the 5 methodology skills (source of truth)
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
