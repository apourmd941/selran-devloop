# Phase 4 — Findings (run wrapper + PR gate)

**Date:** 2026-05-20
**Goal:** `autoloop run <repo>` — the one command that takes a repo from "audit it"
to a reviewable PR, end to end, with the base branch never touched.

## Status: CLI built + orchestration verified; live run gated (same as Phase 3)

| Sub-step | Status |
|---|---|
| `cli/autoloop` (`run` command, preflight, flags) | ✅ built |
| Branch isolation via `git worktree`; base branch untouched | ✅ verified |
| Driver invocation (dry-run path) + run-report assembly + PR-body generation | ✅ verified via `--dry-run` |
| Empty-branch cleanup (no commits → no leftover branch) | ✅ verified |
| Live run (sandbox container + driver + push + open PR) | ⛔ gated on `ANTHROPIC_API_KEY` in the sandbox + real spend |

## What was verified (no API spend, no push, no PR)

`autoloop run <throwaway-repo> --dry-run`:
- preflight passed (git repo + `origin` remote);
- cut `claude/autoloop-<ts>` as a worktree off `main`;
- ran the driver `--dry-run` in the worktree → converged 5 → 0 findings, `green`;
- read `.devloop/last-run.json` and assembled a clean PR body (summary, per-iteration
  findings delta, budget, commit log, review-gate note);
- printed the PR it *would* open (no push, no `gh`);
- removed the worktree **and deleted the empty branch**; `main` untouched.

## Design decisions

- **`git worktree`, not a fresh clone.** The loop runs on an isolated worktree
  branch off the user's repo. The user's working checkout is never moved or dirtied,
  and (in the live path) the container bind-mounts the worktree so commits land on
  the host immediately — git is the transfer, the container stays disposable.
- **Host holds the credentials.** `gh` (PR) and `git push` run on the host where
  they're already authed; only `ANTHROPIC_API_KEY` is passed into the container, and
  only for the loop. No secrets baked into the image.
- **PR is the only write to a shared ref.** autoloop pushes the feature branch and
  opens a PR; it never pushes to or merges `base`. No commits → no PR, branch deleted.
- **Stop-reason-aware.** The PR body surfaces the driver's stop reason (green / stuck
  / budget), so a "stuck — needs human review" run is obvious at a glance.

## What the live run still needs (identical to the Phase 3 gate)

1. **`ANTHROPIC_API_KEY` in the sandbox** — the live path runs the driver, which
   authenticates Claude Code through the key. autoloop's preflight refuses a live run
   without it.
2. **A sandbox image rebuild** — the image now carries Python + the driver (Phase 3
   Dockerfile change); not yet rebuilt/validated for a live run.
3. **Cost + time** — a live run executes app-audit + audit-fix autonomously; budget
   caps (from `autoloop.toml`) bound it.

To do a live run once a key is available:

```bash
export ANTHROPIC_API_KEY=...        # on the host; passed into the container
cli/autoloop run /Users/aidin/NeutronDev/selran-mail-v4 --base main-v4
```

## Carry-forward

- This completes the build-out: cartographer → pre-commit/harness → app-audit →
  audit-fix → driver → autoloop. Phase 5 (repeatability) is "run `autoloop` on a
  second repo with only an `autoloop.toml` + a harness scaffold" — no new code.
- The first real end-to-end run (v4, live) is the natural acceptance test once the
  API key is wired into the sandbox.
