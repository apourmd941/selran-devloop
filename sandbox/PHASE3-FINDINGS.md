# Phase 3 — Findings (Agent SDK loop driver)

**Date:** 2026-05-20
**Goal:** the autonomous run → find → fix → repeat driver that ties the four skills
into an unattended loop with budget caps, stuck-detection, and a clean stop.

## Status: driver built + orchestration verified; live run pending API auth

| Sub-step | Status |
|---|---|
| `driver/devloop.py` (Agent SDK loop driver) | ✅ built |
| State machine, budget caps, stuck-detector, branch guard, stop conditions | ✅ verified via `--dry-run` |
| Sandbox can host the driver (Python + `claude-agent-sdk` in the image) | ✅ added to Dockerfile |
| Live unattended run on v4 (fixes ≥1 real finding) | ⛔ pending — needs `ANTHROPIC_API_KEY` in the sandbox + real API spend |

## What was verified (no API spend)

`python3 driver/devloop.py --repo <branch> --dry-run` exercises the full control
flow against a stub agent that converges 5 → 3 → 1 → 0 open findings:

```
iteration 1: audit → 5 open;  fix → fixed=2 open=3
iteration 2: audit → 3 open;  fix → fixed=2 open=1
iteration 3: audit → 1 open;  fix → fixed=2 open=0
stop_reason: "green: all findings resolved"  (3 iterations, tokens + cost tracked)
```

Also verified:
- **Branch guard** — running on `main` is REFUSED (exit 1) before any work.
- **Stuck-detector** — when fixes stop landing, the loop stops with
  `stuck: ... needs human review` instead of spinning.
- **Budget caps** — `Budget.exhausted()` stops on max iterations / tokens /
  wall-clock; `ResultMessage.usage` + `total_cost_usd` feed the running totals.

## Correct Agent SDK usage (confirmed against the SDK source)

The driver uses the **Claude Agent SDK** (`claude-agent-sdk`) — Claude Code as a
library — NOT the `anthropic` Messages SDK or Managed Agents. That's the right
surface: it runs Claude Code *locally*, loading our skills from `~/.claude/skills`
and operating in our sandbox, whereas Managed Agents would run on Anthropic infra
with its own container and uploaded skills.

Confirmed from `claude-agent-sdk-python` source:
- `skills=[...]` on `ClaudeAgentOptions` is the single switch that enables skills
  (it wires `setting_sources` + the `Skill` tool automatically).
- `permission_mode="bypassPermissions"` is valid; used sandbox-only.
- `ResultMessage` carries `total_cost_usd`, `usage`, `num_turns`, `is_error`,
  `result` — the budget/stop signals.
- Prompt caching is automatic (Claude Code caches the prefix); no manual
  `cache_control` at this layer.

## What the live run still needs

1. **`ANTHROPIC_API_KEY` in the sandbox container** — the Agent SDK authenticates
   through Claude Code; without a key there's no way to run a real turn. (This is
   Phase 3's analogue of Phase 1's "no container runtime installed" gate.)
2. **A sandbox image rebuild** — the Dockerfile now installs `python3`, `pip`, and
   the driver requirements (`claude-agent-sdk`, `anyio`) and copies `driver/` to
   `/opt/devloop/driver/`. Not yet rebuilt/validated in-container.
3. **Acceptance of cost + time** — a live run executes app-audit + audit-fix
   autonomously on v4; that's real token spend over many minutes. Budget caps
   (default 10 iters / 2M tokens / 120 min) bound it.

To do the live run once a key is available:

```bash
# in the sandbox, on an isolated branch, with ANTHROPIC_API_KEY exported:
python3 /opt/devloop/driver/devloop.py --repo /work --config /work/.devloop/autoloop.toml
```

## Carry-forward

- Wire the driver into `autoloop run` (Phase 4): cut branch → clone into sandbox →
  run driver → push branch → open PR with the run report.
- The audit/fix prompts ask the skills to print `DEVLOOP_*` sentinel lines; if a
  skill's output drifts, the driver falls back to the prior open-count. Consider
  the SDK's `structured_output` for a stricter contract later.
