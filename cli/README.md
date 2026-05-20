# cli/ — Phase 4

The `autoloop` CLI — the user-facing entry point.

**Not built yet.** Target usage:

```bash
autoloop run <repo> [branch]    # cut branch, clone into sandbox, run the loop,
                                # push branch, open a PR with a run report
```

The PR is the review gate: you review the diff + run report, merge when satisfied.
Nothing auto-touches `main`. See `docs/DESIGN.md` §5 Phase 4.
