# driver/ — Phase 3 (built; orchestration verified, live run pending)

`devloop.py` — the autonomous loop driver, built on the **Claude Agent SDK**
(`claude-agent-sdk`, Claude Code as a library). Each iteration runs a Claude Code
turn that invokes the four skills by name; the driver supplies the orchestration
the skills don't.

## What it does

```
loop:
  audit turn  — refresh cartographer, run app-audit (which runs pre-commit + harness)
              → parse DEVLOOP_FINDINGS: <n>
  if n == 0   → STOP (green)
  fix turn    — run audit-fix (per-fix verify, revert, defer-after-2)
              → parse DEVLOOP_FIXED/DEFERRED/OPEN
  STOP if: open == 0 (green) | no progress (stuck) | budget exhausted
```

- **Skills enabled** via the SDK's `skills=[...]` option (the one place that turns
  skills on; the SDK wires `setting_sources` + the `Skill` tool itself).
- **Model** `claude-opus-4-7`; `permission_mode="bypassPermissions"` (sandbox-only).
- **Budget caps**: max iterations / tokens (summed from `ResultMessage.usage`) /
  wall-clock. **Stuck-detector**: stops when open findings stop dropping. **Branch
  guard**: refuses to run on `main`/`master`. **Prompt caching** is automatic
  (Claude Code caches the prefix; nothing to configure here).
- The driver never edits code itself — audit-fix does, with per-fix verification.

## Run it

```bash
# Verify the control flow with zero API spend (no SDK install needed):
python3 driver/devloop.py --repo /path/to/branch-checkout --dry-run

# Live (inside the sandbox, with ANTHROPIC_API_KEY set):
python3 driver/devloop.py --repo /work --config /work/.devloop/autoloop.toml
```

A run report (JSON) is written to `<repo>/.devloop/last-run.json`.

## Status

The driver + full orchestration are **built and verified via `--dry-run`** (state
machine, budget accounting, stuck-detection, branch guard, stop conditions — it
converges 5→0 findings and stops green). The **live autonomous run on v4** is the
remaining step, gated on `ANTHROPIC_API_KEY` in the sandbox + real API spend — see
`sandbox/PHASE3-FINDINGS.md`.
