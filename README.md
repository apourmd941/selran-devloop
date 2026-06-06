# Selran DevLoop

An autonomous, repeatable dev-loop for any of the Selran apps. Point it at a repo;
it runs **cartographer → app-audit → audit-fix** in a loop inside a disposable
Linux sandbox until the oracles are green, then hands back reviewable commits as a
pull request.

## What this is (and isn't)

- **Is:** the engine that drives the four skills to convergence, in a sandbox, on
  an isolated branch, with budget caps and a human review gate.
- **Is not:** any one app. DevLoop operates *on* your repos (selran-mail-v4,
  librarian, Cortex, …); they don't live here. Each target repo just gets a
  `.devloop/autoloop.toml`.

## The four skills (source of truth lives here)

`skills/` is now the canonical home for the methodology skills — replacing the old
LocalDrop copies. A tagged DevLoop release pins a known-good combination of all
four, which is what kills the version drift we used to hit.

| Skill | Version | Role |
|---|---|---|
| cartographer | 0.4.1 | Maps the codebase (`.codemap/*.json`) |
| pre-commit-verification | 0.5.1 | Runs tests + the smoke/integration harness |
| app-audit | 0.5.0 | Convergent audit; folds pre-commit + harness results into AUDIT_LOG |
| audit-fix | 0.5.0 | Fixes findings safely (per-fix verify, revert-on-fail) |

## Installing — pick what you want

One interactive installer explains each option and copies what you pick to
`~/.claude/skills/`:

```bash
./install.sh
```

It offers:

- **One skill at a time** — cartographer, pre-commit-verification, app-audit, or
  audit-fix (with their dependencies pulled in automatically).
- **All four skills** (`./install.sh --all`) — the recommended methodology-only
  setup. Use the skills directly from Claude Code without the autonomous loop.
- **Full DevLoop engine** (`./install.sh --devloop`) — all four skills + the
  `autoloop` runner that drives cartographer → app-audit → audit-fix to
  convergence and opens a reviewable PR. Verifies Python / Agent SDK / `gh` /
  API key as part of the install.

`./install.sh --help` prints the same menu without installing anything, so a
new user can read what each piece does before choosing.

## Layout

```
install.sh               friendly installer (interactive picker)
skills/                  the 4 methodology skills (source of truth)
sandbox/                 the reproducible Linux container image (Phase 1)
driver/                  the Agent SDK loop driver (Phase 3)
cli/                     the `autoloop` CLI (Phase 4)
templates/               per-repo config template (autoloop.toml.example)
scripts/install-skills.sh  legacy "install all 4 skills" non-interactive helper
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
| 5 | Repeatability | ✅ proven on Cortex (Python) — config-only |

The one outstanding item is the first **live** end-to-end run, gated on
`ANTHROPIC_API_KEY` in the sandbox + real API spend (the same kind of gate as
Phase 1's container runtime). See `sandbox/PHASE{1..5}-FINDINGS.md` and
`docs/ONBOARDING.md`.

## Hard rules (carried into every phase)

- Never run against `main` — always an isolated branch, always in the sandbox.
- Never put real secrets in the sandbox — throwaway/file-based keys only.
- Per-fix verification + revert-on-failure (audit-fix enforces this).
- Human review gate: the loop opens a PR; you merge. Nothing auto-touches main.
