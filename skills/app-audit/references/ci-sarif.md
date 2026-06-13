# CI/CD integration — SARIF, code-scanning, merge gates

How greenloop findings reach the places developers already work — the GitHub
Security tab and inline PR annotations, the GitLab MR diff, the VS Code Problems
panel — without greenloop shipping any UI of its own. The mechanism is **SARIF
2.1.0**, the standard analysis-results format every major platform ingests.

## The pipeline

```
app-audit  →  .audit/status.json (findings_list)  →  greenloop-sarif.py  →  greenloop.sarif
                                                                          ↘  gl-code-quality.json (GitLab)
```

- `.audit/status.json` already carries the findings (Step 5.6). For inline
  annotations it must include the optional **`findings_list`** array
  (per-finding objects with `file:line`; see `workflow-reporting.md` §1) —
  without it the SARIF run is valid but empty, and the converter says so.
- `scripts/greenloop-sarif.py` converts it. SARIF for GitHub / IDEs;
  `--gitlab-codequality` for GitLab's Code Quality report.

## SARIF mapping (what the converter does)

| greenloop | SARIF |
|---|---|
| severity critical / high | `level: error` + `security-severity` 9.5 / 8.0 |
| severity medium | `level: warning` (5.0) |
| severity low / info | `level: note` (3.0) / `none` (0.0) |
| `category` + `class`/`type` | `ruleId` `greenloop/cat<N>/<class>` |
| `id` + `location` | `partialFingerprints` (cross-run alert de-dup) |
| `location` `file:line[-line]` | `physicalLocation` with a `region` |

`security-severity` is the GitHub convention that drives code-scanning's
sort and alert thresholds. `partialFingerprints` are why a finding that moves a
few lines between runs updates its existing alert instead of opening a duplicate
— the dedup the PR-comment path (Phase 6) does manually, the platform does for
free on SARIF.

## GitHub Actions

Copy `ci/github/greenloop-audit.yml` to `.github/workflows/`. It:

1. triggers on the **`greenloop-audit`** label (or manual dispatch),
2. checks out with `fetch-depth: 0` (git blame → new/pre-existing provenance),
3. installs greenloop + runs `greenloop-doctor` (so the detector tiers are live
   in CI, not silently degraded),
4. runs the audit headless (Claude Agent SDK, needs the `ANTHROPIC_API_KEY`
   secret) → `.audit/status.json`,
5. converts to SARIF and uploads via `github/codeql-action/upload-sarif@v3` →
   findings appear in the **Security tab and inline on the PR diff**,
6. **gates the merge** on open Critical/High with `jq` (drop the step for
   advisory-only).

Required `permissions: security-events: write` is what lets the upload land.

## GitLab CI

`include` `ci/gitlab/greenloop-ci.yml`. Same flow; emits both the SARIF artifact
and a **Code Quality report** (`reports.codequality`) that GitLab renders inline
on the MR diff. Needs a masked `ANTHROPIC_API_KEY` CI variable.

## The merge gate

Both templates fail the job when `status.json` shows open Critical or High:

```bash
crit=$(jq '.findings.open.critical // 0' .audit/status.json)
high=$(jq '.findings.open.high // 0' .audit/status.json)
[ "$crit" -gt 0 ] || [ "$high" -gt 0 ] && exit 1
```

This is the same `status.json` contract CI already consumes (G7) — the gate is
one `jq` line, no greenloop-specific tooling on the runner beyond Python for the
converter. Relax the filter (e.g. critical-only) or delete the step for an
advisory pipeline that annotates without blocking.

## Honest note on the headless run

The convert/upload/gate half of this is plain, dependency-light, and fully
runnable today (the converter is validated against the SARIF 2.1.0 shape and
GitLab CQ in the repo). The *audit* half assumes a headless greenloop run via
the Claude Agent SDK driver (`cli/autoloop`, see `docs/ONBOARDING.md`) producing
`status.json` — that's the one step needing an API key and real spend, the same
gate as any agent-in-CI. A team that runs greenloop locally and commits
`.audit/status.json` can use the SARIF upload + gate with no API key in CI at
all.
