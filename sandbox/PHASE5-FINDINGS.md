# Phase 5 — Findings (repeatability)

**Date:** 2026-05-20
**Goal:** prove a second app runs through the loop with **config-only changes** —
no edits to the DevLoop code.

## Status: ✅ proven (orchestration); live run gated as always

DevLoop was built against **your-rust-app (Rust backend)**. Phase 5 ran it on
**your-python-app (Python backend + Vite/Playwright frontend)** — a different stack — by
adding **one file**: `your-python-app/.devloop/autoloop.toml`. Zero changes to `skills/`,
`sandbox/`, `driver/`, or `cli/`.

```
$ cli/autoloop run /path/to/your-python-app --dry-run
[autoloop] repo=…/your-python-app base=main-v2 branch=claude/autoloop-20260520-163738 dry_run=1
  iter 1: 5 open → fixed 2 → 3 open
  iter 2: 3 open → fixed 2 → 1 open
  iter 3: 1 open → fixed 2 → 0 open
  stop_reason: green: all findings resolved
  PR body generated (base main-v2); worktree + empty branch cleaned up
```

Verified afterwards: your-python-app still on `main-v2` at the same commit, the autoloop
branch deleted, and the only change is the untracked `.devloop/autoloop.toml`. The
pre-existing your-python-app Cowork worktree was untouched.

## Why this is the repeatability guarantee

The cross-stack jump (Rust → Python) is the point: the same engine drove a repo it
was never built against, and the only per-repo input was a config file. What stayed
generic:

- **skills/** — cartographer / pre-commit-verification / app-audit / audit-fix
- **sandbox/Dockerfile** — one image (Rust + Node + Python + Postgres + Playwright)
- **driver/devloop.py** and **cli/autoloop** — repo-agnostic

What changes per repo: an `autoloop.toml` (build/launch/harness/budget) plus a
harness scaffold (the per-repo oracle work, one-time). Documented in
`docs/ONBOARDING.md`.

## Notes / carry-forward

- your-python-app's `.devloop/autoloop.toml` was left **untracked** in the your-python-app repo (a
  reversible, config-only change) — commit it there when you want your-python-app permanently
  onboarded. The launch/health/db fields carry `CUSTOMIZE` markers; fill them from
  your-python-app's actual server before a live run.
- your-python-app already ships frontend e2e (`frontend/playwright.config.ts`, `tests-e2e/`),
  so its harness needs less scaffolding than v4's did.
- The **live run** (real audit-fix loop + real PR) is gated on `ANTHROPIC_API_KEY`
  in the sandbox + real spend — the same single gate that stands in front of every
  live run (Phases 3–5). autoloop's preflight refuses a live run without the key.

## The build-out is complete

```
cartographer → pre-commit/harness → app-audit → audit-fix → driver → autoloop
```

Phases 1–5 are built and verified. The one outstanding item across the whole project
is the first **live** end-to-end run, gated on wiring `ANTHROPIC_API_KEY` into the
sandbox — the same kind of gate as Phase 1's container runtime, which was then
unblocked and passed.
