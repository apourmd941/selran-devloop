# cli/ — Phase 4 (built; orchestration verified, live run gated)

`autoloop` — the user-facing entry point that runs the whole flow end to end.

```bash
autoloop run <repo> [--base <branch>] [--scope <text>] [--dry-run]
```

## What `autoloop run` does

1. **Preflight** — git repo, `origin` remote, `gh` auth, container runtime (live only).
2. **Cut an isolated worktree branch** `claude/autoloop-<ts>` off the base branch
   (a `git worktree`, so the user's checkout is untouched).
3. **Run the loop on that branch:**
   - **live:** build the sandbox image, run the container with the worktree
     bind-mounted at `/work`, stand up Postgres + pgvector + secret-service, then run
     the Phase 3 driver (cartographer → app-audit → audit-fix, committing each fix).
     Commits land on the host worktree (git is the transfer).
   - **`--dry-run`:** run the driver with `--dry-run` on the worktree — no container,
     no API spend, no commits.
4. **Push** the branch to origin (only if commits were produced).
5. **Open a PR** with a run report (stop reason, per-iteration findings delta, budget,
   commit log). Empty/no-commit runs delete the branch instead.

The PR is the review gate: you review the diff + report and merge. **autoloop never
pushes to or merges the base branch.**

## Status

Built and **verified via `--dry-run`**: preflight → worktree branch → driver run →
report assembly → PR-body generation → cleanup, with the base branch untouched and
the empty branch cleaned up. The **live run** is gated on the same thing as Phase 3
— `ANTHROPIC_API_KEY` in the sandbox + real API spend. See `sandbox/PHASE4-FINDINGS.md`.
