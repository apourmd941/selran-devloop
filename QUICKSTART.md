# Greenloop in 60 seconds

**Install** (inside Claude Code):

```
/plugin marketplace add apourmd941/selran-devloop
/plugin install greenloop@selran
```

**Run** — open any repo and say:

> **quick audit**

That's it. No config, no spec, no setup questions. In a few minutes you get:

- real analyzers run first (secrets, dependency CVEs, SAST — and greenloop
  tells you which tiers it actually had, never pretending),
- a focused review of Security / Error handling / Resource bounds, riskiest
  files first (code churn × test coverage),
- findings with `file:line`, severity, confidence, and a concrete failing
  scenario — every claim self-challenged before you see it,
- an `AUDIT_LOG.md` + machine-readable `.audit/status.json` in your repo.

A quick audit ends by telling you exactly what it *didn't* do — it's a smoke
detector, not a clearance.

**When you want more:**

| Say | You get |
|---|---|
| `audit` | the standard loop: codemap, agreed scope, all 10 categories available, blind adversarial challenge, full artifacts |
| `deep audit` | everything: parallel reviewers, optional second-model challenge, clean-room verification, dashboard + traceability |
| `review my PR` | change-scoped review; findings can post as PR comments or SARIF code-scanning alerts |
| `fix the findings` | audit-fix: safest-order fixes, each verified and truth-score-gated, with rollback |

**Make the findings stronger** (optional, one time):

```bash
./install.sh --doctor --install     # adds semgrep / osv-scanner / gitleaks
```

**Where things land:** `AUDIT_LOG.md` (the durable record), `TECHNICAL_DEBT.md`
(what you've chosen to live with), `.audit/status.json` (CI gate:
`jq '.findings.open.critical == 0'`), `.audit/dashboard.html` (self-contained
findings board). Full docs: [README.md](README.md).
