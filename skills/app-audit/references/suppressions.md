# Suppressions — .greenloopignore, inline markers, and the governance rules

How a team durably says "we accept this" without the ignore-file rot that
plagues every other analyzer. The core difference: greenloop suppressions are
**governed** — they require reasons, Critical suppressions require expiry
dates, expired suppressions stop working, and the suppression set is itself
audited every round. A suppression here is a *decision on the record*, not a
hole in the net.

## The two mechanisms

**1. `.greenloopignore`** (repo root) — one suppression per line:

```
<path-glob>[:<line>] [<rule-glob>] -- <reason ...> [expires:YYYY-MM-DD] [owner:<name>]

vendor/**                               -- third-party code, not ours
src/legacy/** cat6/*                    -- legacy subsystem, sunset planned expires:2026-09-30 owner:aidin
api/search.py:41 cat3/sql-injection     -- FP: value from a closed enum expires:2026-12-01
```

**2. Inline marker** — on the finding's line or the line directly above:

```ts
// greenloop:ignore[cat3/secret-in-log] prefix is redacted upstream expires:2026-12-01
console.log(`auth ok, token=${prefix}`);
```

Rule-globs match the finding's rule id tail `cat<N>/<class>` (the same ids the
SARIF export uses); omit for `*`. Path matching is fnmatch globs; a `:line`
suffix pins the suppression to one line.

## The governance rules (what makes this different)

| Rule | Behavior |
|---|---|
| **No reason → invalid** | The line is ignored, the finding still reports, and the meta-audit flags the line. A suppression nobody can explain is a blind spot, not a decision. |
| **Critical requires expiry** | A Critical finding can be *paused* (`expires:`), never *buried*. Without an expiry the suppression is refused and reported. |
| **Expired → reopens** | Past `expires:`, the suppression stops suppressing — the finding is OPEN again and the entry is flagged for re-decision. "Deferred" cannot silently become "forever". |
| **Suppressed ≠ deleted** | Suppressed findings keep their full record: status `suppressed` in `findings_list`, their own severity buckets in `status.json.findings.suppressed`, a SARIF `suppressions` object (platforms show "dismissed with reason"), and a collapsed section in the report. |
| **Gate-safe by construction** | The CI merge gate reads `findings.open.*`; suppression moves findings out of `open`, so the gate honors team decisions with no extra logic. |

## The meta-audit (suppressions get audited too)

Every application of the suppression set reports:

- **Expired** entries — no longer suppressing; re-decide or remove.
- **Invalid** entries — missing reason / malformed `expires:`; never applied.
- **Stale** entries — matched 0 findings; the issue was fixed or the path moved.
  Remove the line (dead suppressions are future blind spots).
- **Over-broad** entries — matched >10 findings; one glob hiding a class of
  problems deserves a narrower scope or an explicit team decision.
- **Critical-without-expiry** attempts — refused, listed.

These land in the close report and `status.json.suppressions`; chronic ones
belong in TECHNICAL_DEBT.md like any other accepted risk.

## Running it

```bash
python3 scripts/greenloop-suppress.py \
  --status .audit/status.json --ignore .greenloopignore \
  --repo . --scan-inline --out .audit/status.json
```

The audit applies this at Step 4.6 (after the adversarial challenge, before
close); CI templates can run it between the audit and the SARIF conversion.
Exit code is always 0 — governance reports, the *gate* decides.

## Suppression vs. the cleared registry vs. deferral (don't confuse them)

| Mechanism | Who decides | Means |
|---|---|---|
| **Cleared registry** (chronicle, G6) | the audit's own challenge | "this claim was *refuted* — it's not a real finding on this code" |
| **Suppression** (this doc) | the team | "this finding is real (or contested), and we *accept/park* it deliberately" |
| **Deferred status** (AUDIT_LOG) | the user, per finding, per round | "fix later" — work-queue state, shows in TECHNICAL_DEBT.md |

A false positive should die in the challenge (and registry) — suppressing it
works but wastes the registry's learning. Accepted true positives are exactly
what suppressions are for.
