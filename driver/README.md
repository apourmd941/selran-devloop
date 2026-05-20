# driver/ — Phase 3

The Agent SDK loop driver: the autonomous process that runs
cartographer → app-audit → audit-fix → re-audit in a loop until the oracles are
green, stuck, or budget-exhausted.

**Not built yet.** Key design decisions (see `docs/DESIGN.md` §5 Phase 3):
- stuck-fix policy: try ≤2 alternative fixes, then mark `deferred — needs human`
- budget caps: max iterations / tokens / wall-clock + kill switch
- stop conditions: green | stuck | budget
- branch isolation, commit-per-fix, prompt caching on
- loads the four skills from `~/.claude/skills` as its methodology
