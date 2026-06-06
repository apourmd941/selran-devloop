# Onboard a new repo to DevLoop

DevLoop operates *on* your repos; onboarding a new one is **config + a harness
scaffold**, not code changes to DevLoop itself. Proven on your-python-app (Python) after
being built against your-rust-app (Rust) — same engine, different stack, only a
config file added.

## 1. Install (once per machine)

```bash
git clone <selran-devloop>            # or pull latest
cd selran-devloop && ./install.sh     # interactive picker — explains each option
```

`./install.sh` lets you pick exactly what you want: a single skill (cartographer,
pre-commit-verification, app-audit, audit-fix), all four together
(`./install.sh --all`), or the full DevLoop engine including the autonomous
runner (`./install.sh --devloop`). Pass `--help` to see the menu without
installing. The skills land in `~/.claude/skills/` where Claude Code loads them.

## 2. Add a per-repo config (the only required file)

Copy the template and tune it for the target repo:

```bash
mkdir -p /path/to/target-repo/.devloop
cp templates/autoloop.toml.example /path/to/target-repo/.devloop/autoloop.toml
$EDITOR /path/to/target-repo/.devloop/autoloop.toml
```

What to set (everything else has defaults):
- `[repo] default_branch`, `scope`
- `[build]` / `[launch]` — how the backend builds + launches, the health URL
- `[harness] categories` — which smoke categories apply to this stack
- `[loop]` — budget caps; add the repo's primary branch to `never_touch_branches`
- `[db]` — only if the migration smoke applies

## 3. Scaffold the smoke harness (per-repo, one-time)

The harness is the oracle layer — the loop only converges on what a test can flag.
Run pre-commit-verification against the repo; if it's a runnable app with no harness,
it offers to scaffold the templates from
`skills/pre-commit-verification/references/harness/`, then you customize the marked
points (routes, screens, providers) for that repo's stack. (A repo that already has
e2e — like your-python-app's `playwright.config.ts` — needs less.)

This is the only per-repo *work*; everything else is config.

## 4. Run it

```bash
# Verify the orchestration with no API spend:
cli/autoloop run /path/to/target-repo --dry-run

# Live (needs ANTHROPIC_API_KEY for the loop; opens a PR you review):
export ANTHROPIC_API_KEY=...
cli/autoloop run /path/to/target-repo --base <branch>
```

`autoloop` cuts an isolated worktree branch, runs cartographer → app-audit →
audit-fix in the sandbox, pushes the branch, and opens a PR with a run report. Your
base branch is never touched; you review the PR and merge.

## What does NOT change per repo

- The four skills (`skills/`) — generic.
- The sandbox image (`sandbox/Dockerfile`) — generic toolchain (Rust + Node + Python
  + Postgres + Playwright). If a repo needs an extra system dep, add it once to the
  image; it doesn't fork per repo.
- The driver (`driver/devloop.py`) and the CLI (`cli/autoloop`) — generic.

So a new repo = an `autoloop.toml` + a harness scaffold. That's the repeatability
guarantee.
