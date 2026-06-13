# Detector toolchain — readiness + bundled offline SAST

Greenloop's highest-confidence findings are **grounded in real analyzers**
(app-audit Step 3.0). A model's read is a hypothesis; a semgrep hit or an OSV
CVE is a fact. When a detector is absent, that grounding silently disappears and
findings degrade to judgement-only — lower confidence, more false positives. This
directory makes the toolchain *visible and present* instead of assumed.

## `greenloop-doctor` — readiness probe (`scripts/greenloop-doctor.sh`)

Reports which detector **tiers** are live for the current repo, and the exact
install command for what's missing:

```
$ scripts/greenloop-doctor.sh
Greenloop detector readiness
  detected stack: rust python
  ✓ SAST (security/safety)     semgrep 1.166.0   [+ bundled greenloop ruleset]
  ✗ Dependency CVEs            missing — brew install osv-scanner
  ✓ Secrets                    gitleaks 8.30.1
  ✓ Types (python)            mypy
  universal tiers live: 2/3 (missing tiers degrade findings to judgement-only)
```

- `--json` — machine-readable; app-audit reads this at Step 3.0 and records it
  in `status.json.metrics.detectors`.
- `--install` — installs the missing **universal** detectors (semgrep,
  osv-scanner, gitleaks) via Homebrew, after asking.
- Exit `0` iff all three universal tiers are live; `1` otherwise — so CI can gate
  on a fully-grounded toolchain.

**Tier honesty is the whole point.** The probe only credits a dependency
scanner when its ecosystem's manifest is actually present — it will *not* claim
`npm-audit` covers a Rust repo with no `package.json`. A missing tier is
reported, never hidden.

## `greenloop.yml` — bundled offline SAST ruleset

`semgrep --config auto` pulls rules from the semgrep registry over the network:
non-deterministic, and unavailable offline or in a sandboxed CI runner. This
bundled set is the deterministic floor — run it always:

```bash
semgrep --config <plugin>/skills/app-audit/references/detectors/greenloop.yml --json .
```

It is a **curated starter**, not a replacement for `--config auto` — run both
when the network is up. It covers the core, low-false-positive classes:
SQL built by string interpolation, `subprocess(shell=True)` / `os.system`,
unsafe `yaml.load`, credentials written to logs, and `eval`/`new Function` on
non-literals.

**Validated against the benchmark** (`benchmark/`): the ruleset catches the
seeded SQL-injection (`py-sql-injection`) and secret-in-log (`ts-secret-in-log`)
fixtures and produces **zero false positives on their clean controls** — the
redacted-log control specifically does not match (the regex is anchored to an
identifier shape, so `token.slice(0,4)` is not flagged). When you add a rule
here, add or extend a benchmark fixture that exercises it, so the regression gate
protects it.

## How the three layers compose

| Layer | Source | Runs |
|---|---|---|
| Stock detectors | semgrep `--config auto`, osv/trivy, gitleaks, type-checkers | when installed (probe reports) |
| **Bundled offline** | `greenloop.yml` (this dir) | always, no network |
| Learned rules | `.audit/learned-rules/` (per repo, G6) | always, from round 2 on |

All three feed Step 3.0; the LLM adjudicates their union. The doctor guarantees
the first layer is *present or known-absent*; the bundled layer guarantees a
floor even on a bare machine; the learned layer compounds per repo.
