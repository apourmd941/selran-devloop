#!/usr/bin/env python3
"""
Selran DevLoop driver — the autonomous run → find → fix → repeat loop.

Built on the Claude Agent SDK (`claude-agent-sdk`), which runs Claude Code as a
library. Each loop iteration runs a Claude Code turn that invokes the four
methodology skills (cartographer, pre-commit-verification, app-audit, audit-fix)
by name; the driver supplies the orchestration the skills don't: a state machine,
budget caps, a stuck-detector, stop conditions, and a run report.

Design notes:
- The skills do the domain reasoning. The driver decides *when to stop* and
  *contains the blast radius* — it never edits code itself.
- Prompt caching is automatic: the Agent SDK drives Claude Code, which caches the
  prompt prefix across turns. There is no manual cache_control at this layer.
- Runs INSIDE the sandbox, in `cwd` = the cloned target branch. Never against a
  protected branch (guarded below). Needs ANTHROPIC_API_KEY in the environment.
- `--dry-run` exercises the state machine + budget logic with a stub agent, so
  the control flow can be tested with zero API spend and without the SDK installed.

Usage:
    python3 driver/devloop.py --repo /work [--config /work/.devloop/autoloop.toml]
    python3 driver/devloop.py --repo /work --dry-run        # no API calls
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

MODEL = "claude-opus-4-7"
SKILLS = ["cartographer", "pre-commit-verification", "app-audit", "audit-fix"]

# Sentinel lines the skills are asked to print so the driver can parse outcomes
# without screen-scraping prose.
RE_FINDINGS = re.compile(r"DEVLOOP_FINDINGS:\s*(\d+)")
RE_FIXED = re.compile(r"DEVLOOP_FIXED:\s*(\d+)")
RE_DEFERRED = re.compile(r"DEVLOOP_DEFERRED:\s*(\d+)")
RE_OPEN = re.compile(r"DEVLOOP_OPEN:\s*(\d+)")


# --------------------------------------------------------------------------- #
# Config + budget
# --------------------------------------------------------------------------- #
@dataclass
class LoopConfig:
    repo: Path
    scope: str = "the original scope of the latest AUDIT_LOG round"
    max_iterations: int = 10
    max_tokens: int = 2_000_000
    max_wall_clock_minutes: int = 120
    stuck_no_progress_iters: int = 2          # stop if open count doesn't drop for N iters
    never_touch_branches: tuple[str, ...] = ("main", "master")

    @classmethod
    def load(cls, repo: Path, config_path: Path | None) -> "LoopConfig":
        cfg = cls(repo=repo)
        path = config_path or (repo / ".devloop" / "autoloop.toml")
        if path.exists():
            data = _read_toml(path)
            loop = data.get("loop", {})
            cfg.max_iterations = int(loop.get("max_iterations", cfg.max_iterations))
            cfg.max_tokens = int(loop.get("max_tokens", cfg.max_tokens))
            cfg.max_wall_clock_minutes = int(
                loop.get("max_wall_clock_minutes", cfg.max_wall_clock_minutes)
            )
            cfg.stuck_no_progress_iters = int(
                loop.get("stuck_fix_alternatives", cfg.stuck_no_progress_iters)
            )
            nb = loop.get("never_touch_branches")
            if isinstance(nb, list) and nb:
                cfg.never_touch_branches = tuple(str(b) for b in nb)
            repo_tbl = data.get("repo", {})
            if repo_tbl.get("scope"):
                cfg.scope = str(repo_tbl["scope"])
        return cfg


@dataclass
class Budget:
    max_iterations: int
    max_tokens: int
    max_wall_clock_s: float
    started_at: float = field(default_factory=time.monotonic)
    iterations: int = 0
    tokens: int = 0
    cost_usd: float = 0.0

    def record(self, usage: dict | None, cost: float | None) -> None:
        if usage:
            for k in ("input_tokens", "output_tokens",
                      "cache_creation_input_tokens", "cache_read_input_tokens"):
                v = usage.get(k)
                if isinstance(v, (int, float)):
                    self.tokens += int(v)
        if isinstance(cost, (int, float)):
            self.cost_usd += float(cost)

    def exhausted(self) -> str | None:
        if self.iterations >= self.max_iterations:
            return f"max_iterations ({self.max_iterations}) reached"
        if self.tokens >= self.max_tokens:
            return f"max_tokens ({self.max_tokens}) reached"
        if (time.monotonic() - self.started_at) >= self.max_wall_clock_s:
            return f"max_wall_clock ({self.max_wall_clock_s / 60:.0f}m) reached"
        return None


@dataclass
class TurnResult:
    text: str
    usage: dict | None
    cost_usd: float | None
    num_turns: int
    is_error: bool


# --------------------------------------------------------------------------- #
# Agent invocation (real + dry-run)
# --------------------------------------------------------------------------- #
async def run_agent_turn(prompt: str, cfg: LoopConfig, max_turns: int) -> TurnResult:
    """Run one Claude Code turn via the Agent SDK, with our skills enabled."""
    from claude_agent_sdk import (  # imported lazily so --dry-run needs no install
        query,
        ClaudeAgentOptions,
        AssistantMessage,
        TextBlock,
        ToolUseBlock,
        ResultMessage,
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        cwd=str(cfg.repo),
        skills=SKILLS,                    # the single place to enable skills
        permission_mode="bypassPermissions",  # sandbox-only; never on a host
        max_turns=max_turns,
    )

    text_parts: list[str] = []
    result = TurnResult(text="", usage=None, cost_usd=None, num_turns=0, is_error=False)
    # Live activity stream: print each tool call + a one-line narration as the
    # messages arrive, so a long turn shows what Claude is doing instead of going
    # dark. Set DEVLOOP_QUIET=1 to suppress.
    stream = os.environ.get("DEVLOOP_QUIET") != "1"
    err = None
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
                        if stream:
                            line = block.text.strip().splitlines()[0] if block.text.strip() else ""
                            if line:
                                print(f"     » {line[:140]}", flush=True)
                    elif isinstance(block, ToolUseBlock) and stream:
                        print(f"     · {block.name}: {_summarize_tool(block.name, block.input)}",
                              flush=True)
            elif isinstance(message, ResultMessage):
                result.usage = message.usage
                result.cost_usd = message.total_cost_usd
                result.num_turns = message.num_turns
                result.is_error = message.is_error
                if message.result:
                    text_parts.append(message.result)
    except Exception as e:  # noqa: BLE001
        # The SDK raises on e.g. "Reached maximum number of turns". Treat any
        # turn-level failure as a clean error result, not a crash, so the loop
        # stops with a readable stop_reason + report instead of a traceback.
        err = str(e)
        result.is_error = True
        if stream:
            print(f"     ✗ agent error: {err}", flush=True)
    result.text = "\n".join(text_parts)
    if err:
        result.text = (result.text + f"\nAGENT_ERROR: {err}").strip()
    return result


def _summarize_tool(name: str, inp: dict | None) -> str:
    """One-line summary of a tool call for the live stream."""
    inp = inp or {}
    if name == "Bash":
        return str(inp.get("command", ""))[:90]
    if name in ("Read", "Edit", "Write", "NotebookEdit"):
        return str(inp.get("file_path", ""))
    if name == "Grep":
        return f"/{inp.get('pattern', '')}/ {inp.get('path', '') or ''}".strip()
    if name == "Glob":
        return str(inp.get("pattern", ""))
    if name == "Skill":
        return str(inp.get("name") or inp.get("command", ""))
    if name == "Task":
        return str(inp.get("description", ""))[:80]
    return ", ".join(f"{k}={str(v)[:40]}" for k, v in list(inp.items())[:2])


def stub_agent_turn(prompt: str, state: dict) -> TurnResult:
    """Deterministic stand-in for --dry-run: converges from 5 open findings to 0,
    so the state machine, budget accounting, and stop logic can be exercised
    without any API spend. Discriminate on the sentinel each prompt requests
    (the fix prompt asks for DEVLOOP_FIXED; the audit prompt for DEVLOOP_FINDINGS)
    — both prompts contain the word 'audit', so don't branch on that."""
    if "DEVLOOP_FIXED" in prompt:
        # fix turn: resolve two findings per iteration
        open_n = max(0, state.get("open", 5) - 2)
        state["open"] = open_n
        return TurnResult(
            text=f"(dry-run) audit-fix pass. DEVLOOP_FIXED: 2 DEVLOOP_DEFERRED: 0 "
                 f"DEVLOOP_OPEN: {open_n}",
            usage={"input_tokens": 1500, "output_tokens": 800}, cost_usd=0.03,
            num_turns=4, is_error=False,
        )
    # audit turn
    open_n = state.get("open", 5)
    return TurnResult(
        text=f"(dry-run) audit complete. DEVLOOP_FINDINGS: {open_n}",
        usage={"input_tokens": 1000, "output_tokens": 500}, cost_usd=0.02,
        num_turns=3, is_error=False,
    )


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
def audit_prompt(cfg: LoopConfig) -> str:
    return (
        "Refresh the cartographer codemap, then run app-audit on "
        f"{cfg.scope}. app-audit will run pre-commit-verification (including the "
        "smoke harness) as its baseline and fold the results into AUDIT_LOG.md.\n\n"
        "Do NOT fix anything in this turn. When done, print exactly one line:\n"
        "DEVLOOP_FINDINGS: <number of open findings in the latest AUDIT_LOG round>"
    )


def fix_prompt(cfg: LoopConfig) -> str:
    return (
        "Run audit-fix to address the open findings from the latest AUDIT_LOG "
        "round. Order by blast radius, verify each fix with pre-commit-verification, "
        "revert on failure, and after 2 failed attempts on a finding mark it "
        "deferred and continue. Commit each successful fix.\n\n"
        "When done, print exactly one line:\n"
        "DEVLOOP_FIXED: <n> DEVLOOP_DEFERRED: <n> DEVLOOP_OPEN: <remaining open findings>"
    )


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #
def assert_safe_branch(cfg: LoopConfig) -> str:
    branch = _git(cfg.repo, "rev-parse", "--abbrev-ref", "HEAD") or "(unknown)"
    if branch in cfg.never_touch_branches:
        sys.exit(
            f"REFUSED: current branch '{branch}' is protected "
            f"({', '.join(cfg.never_touch_branches)}). DevLoop only runs on an "
            "isolated branch — check out a working branch first."
        )
    return branch


async def run_loop(cfg: LoopConfig, dry_run: bool) -> dict:
    budget = Budget(
        max_iterations=cfg.max_iterations,
        max_tokens=cfg.max_tokens,
        max_wall_clock_s=cfg.max_wall_clock_minutes * 60,
    )
    branch = assert_safe_branch(cfg)
    print(f"[devloop] repo={cfg.repo} branch={branch} dry_run={dry_run}")

    stub_state = {"open": 5}
    history: list[dict] = []
    prev_open: int | None = None
    no_progress = 0
    stop_reason = "unknown"

    while True:
        reason = budget.exhausted()
        if reason:
            stop_reason = f"budget: {reason}"
            break
        budget.iterations += 1
        it = budget.iterations
        print(f"\n[devloop] === iteration {it} ===")

        # 1) map + audit
        if not dry_run:
            print("[devloop] audit turn — cartographer refresh + app-audit "
                  "(live activity below; can take several minutes)…", flush=True)
        a = (stub_agent_turn(audit_prompt(cfg), stub_state) if dry_run
             else await run_agent_turn(audit_prompt(cfg), cfg, max_turns=250))
        budget.record(a.usage, a.cost_usd)
        if a.is_error:
            detail = a.text.split("AGENT_ERROR:", 1)[-1].strip() if "AGENT_ERROR:" in a.text else ""
            stop_reason = f"agent error during audit turn{(' — ' + detail) if detail else ''}"
            history.append({"iter": it, "phase": "audit", "error": detail or True})
            break
        m = RE_FINDINGS.search(a.text)
        open_n = int(m.group(1)) if m else None
        print(f"[devloop] audit → open findings: {open_n}")

        if open_n == 0:
            history.append({"iter": it, "phase": "audit", "open": 0})
            stop_reason = "green: no open findings"
            break
        if open_n is None:
            stop_reason = "could not parse audit findings count (DEVLOOP_FINDINGS missing)"
            history.append({"iter": it, "phase": "audit", "open": None})
            break

        # stuck detection: open count not decreasing across iterations
        if prev_open is not None and open_n >= prev_open:
            no_progress += 1
        else:
            no_progress = 0
        prev_open = open_n

        reason = budget.exhausted()
        if reason:
            stop_reason = f"budget: {reason}"
            break

        # 2) fix
        if not dry_run:
            print(f"[devloop] fix turn — audit-fix on {open_n} finding(s) "
                  "(live activity below)…", flush=True)
        f = (stub_agent_turn(fix_prompt(cfg), stub_state) if dry_run
             else await run_agent_turn(fix_prompt(cfg), cfg, max_turns=400))
        budget.record(f.usage, f.cost_usd)
        if f.is_error:
            detail = f.text.split("AGENT_ERROR:", 1)[-1].strip() if "AGENT_ERROR:" in f.text else ""
            stop_reason = f"agent error during fix turn{(' — ' + detail) if detail else ''}"
            history.append({"iter": it, "phase": "fix", "error": detail or True})
            break
        fixed = int(RE_FIXED.search(f.text).group(1)) if RE_FIXED.search(f.text) else 0
        deferred = int(RE_DEFERRED.search(f.text).group(1)) if RE_DEFERRED.search(f.text) else 0
        remaining = int(RE_OPEN.search(f.text).group(1)) if RE_OPEN.search(f.text) else open_n
        print(f"[devloop] fix → fixed={fixed} deferred={deferred} open={remaining}")
        history.append({"iter": it, "open_before": open_n, "fixed": fixed,
                        "deferred": deferred, "open_after": remaining})

        if remaining == 0:
            stop_reason = "green: all findings resolved"
            break
        if fixed == 0 or no_progress >= cfg.stuck_no_progress_iters:
            stop_reason = (
                f"stuck: no progress for {cfg.stuck_no_progress_iters} iteration(s) "
                f"({deferred} deferred, {remaining} open) — needs human review"
            )
            break

    report = {
        "branch": branch,
        "stop_reason": stop_reason,
        "iterations": budget.iterations,
        "tokens": budget.tokens,
        "cost_usd": round(budget.cost_usd, 4),
        "wall_clock_s": round(time.monotonic() - budget.started_at, 1),
        "history": history,
        "dry_run": dry_run,
    }
    return report


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _git(repo: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(repo), *args],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _read_toml(path: Path) -> dict:
    try:
        import tomllib  # py3.11+
        return tomllib.loads(path.read_text())
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="Selran DevLoop autonomous driver")
    ap.add_argument("--repo", required=True, type=Path, help="target repo (the branch checkout)")
    ap.add_argument("--config", type=Path, default=None, help="path to autoloop.toml")
    ap.add_argument("--dry-run", action="store_true", help="exercise the loop with no API calls")
    ap.add_argument("--report", type=Path, default=None, help="write run report JSON here")
    args = ap.parse_args()

    if not args.repo.exists():
        print(f"repo not found: {args.repo}", file=sys.stderr)
        return 2

    cfg = LoopConfig.load(args.repo, args.config)
    import anyio
    report = anyio.run(run_loop, cfg, args.dry_run)

    print("\n[devloop] ===== run report =====")
    print(json.dumps(report, indent=2))
    out = args.report or (args.repo / ".devloop" / "last-run.json")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"[devloop] report written: {out}")
    except Exception as e:  # noqa: BLE001
        print(f"[devloop] could not write report: {e}", file=sys.stderr)

    # Exit non-zero only on hard failure; "green" and "stuck/budget" are clean stops.
    return 1 if report["stop_reason"].startswith("agent error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
