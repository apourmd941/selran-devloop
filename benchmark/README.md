# Greenloop benchmark harness

Turns "greenloop is good" from a claim into a **number**. A corpus of fixtures
carries deliberately-seeded bugs alongside clean control code; an audit run is
scored against that ground truth for **recall** (did it find the seeded bugs?),
**precision / false-positive rate** (did it flag clean code?), and **severity
accuracy**. A committed baseline + regression gate means a skill edit that
lowers quality fails before it merges.

This is the answer to the field's real lead over greenloop — *maturity, not
capability*. You can't prove "unproven," but you can measure it, and you can
protect what you measure as the 16 SKILL files evolve.

## Layout

```
benchmark/
  corpus/                     fixtures — each a dir with source + ground-truth.json
    py-sql-injection/         SQL injection (Critical) + a clean parameterized query
    ts-secret-in-log/         token logged (High) + a redacted-log control
    rs-missing-tx/            two writes, no transaction (High) + a transactional control
    clean-baseline/           entirely clean — any finding here is a pure false positive
  score.py                    the scorer + regression gate (stdlib only, no deps)
  baseline.json               committed scorecard the gate compares against
  examples/
    run-good.json             a perfect run (recall 1.0, 0 FPs) — also seeds the baseline
    run-regressed.json        a degraded run (misses a bug, flags clean code) — the gate rejects it
```

## What each fixture declares (`ground-truth.json`)

```json
{
  "fixture": "py-sql-injection",
  "language": "python",
  "seeded":     [{"id": "SQLI-1", "file": "app.py", "line": 8,
                  "category": 3, "severity": "critical", "class": "sql-injection"}],
  "clean_zones":[{"file": "app.py", "lines": [12, 16],
                  "reason": "parameterized query — flagging this is a false positive"}]
}
```

- **seeded** — the bugs that *must* be found. A finding within ±3 lines of the
  seeded line (same file) counts as a hit (recall) and is checked for severity
  within one level.
- **clean_zones** — code that must *not* be flagged. A finding landing in a
  clean zone is a false positive (precision / fp_rate). The `clean-baseline`
  fixture is wall-to-wall clean zone — a pure hallucination control.
- A finding that is neither on a seed nor in a clean zone is **extra** —
  reported, but unscored. A real auditor legitimately finds things you didn't
  seed; the harness doesn't punish that, it just doesn't credit it.

## Running it

```bash
# score a run
python3 score.py --corpus corpus --findings examples/run-good.json

# re-seed the baseline from a known-good run
python3 score.py --corpus corpus --findings examples/run-good.json \
  --baseline baseline.json --write-baseline

# gate a run (CI): exit 1 if recall/precision drop >0.05 or fp_rate rises >0.05
python3 score.py --corpus corpus --findings run.json --baseline baseline.json --gate
```

Current baseline (from `run-good.json`): **recall 1.0 · precision 1.0 ·
fp_rate 0.0 · severity_accuracy 1.0**. The gate tolerances live in `score.py`'s
`gate()` (default ±0.05) — tighten them as the corpus grows and runs stabilize.

## The agent-execution protocol (how a real audit feeds the scorer)

The scorer is deterministic; producing the `findings.json` is the agent's job.
To benchmark greenloop for real:

1. Point app-audit at each fixture directory (whole-codebase scope, all
   categories). Fixtures are tiny by design — one focused pass each.
2. After the run, emit findings in the normalized shape, keyed by fixture:
   ```json
   { "py-sql-injection": { "findings": [
       {"file": "app.py", "line": 8, "category": 3, "severity": "critical", "title": "..."} ] }, ... }
   ```
   (`file` is matched by basename, so repo-relative or absolute both work.)
3. Run `score.py --gate`. A drop fails the run.

Run it **before cutting a release** (publish the scorecard as the proof) and
**in CI on every change to `skills/`** (the regression gate). The same harness
that proves quality to users protects it from your own future edits.

## Honest scope — what this does and doesn't measure

- **Measures:** detection quality (recall / precision / FP-rate / severity) on
  *seeded* bug classes. The corpus is the spec of "what greenloop should catch";
  growing it is how coverage grows.
- **Does not measure (yet):** *convergence* — rounds-for-audit-fix-to-clean a
  fixture. That needs the fix loop in the run and is a natural follow-on
  (`fix-benchmark`): seed a bug, run audit→fix→re-audit, count rounds and assert
  the seeded bug is gone and no clean control got "fixed."
- **Not a substitute for real-world runs.** A seeded corpus measures the bug
  classes you thought to seed. It catches *regressions* in known-good behavior;
  it does not discover blind spots. Field feedback still finds those — the
  corpus is where each newly-discovered blind spot gets *added* so it can never
  regress again.

## Adding a fixture (this is the main maintenance task)

1. `mkdir corpus/<lang>-<bug-class>/`, drop in a tiny source file with **one**
   seeded bug and at least one clean control beside it.
2. Write `ground-truth.json` pointing at the seeded line(s) and clean zone(s).
3. Re-run a known-good audit, regenerate `baseline.json` with `--write-baseline`,
   commit both. Each real-world miss greenloop has should become a fixture here —
   that's how the benchmark compounds into a moat.
