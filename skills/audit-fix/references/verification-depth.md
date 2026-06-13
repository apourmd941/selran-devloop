# Verification depth — truth scores, clean-room re-runs, blind authoring, witness

The mechanics behind audit-fix Step 2.3d (truth score), Step 2.3c's blind
authoring contract, Step 5.0 (clean-room close + witness), and
pre-commit-verification's clean-room / witness modes. The shared idea: a fix is
only as "fixed" as the evidence behind it, and the evidence itself must be
hard to rig.

## §1 — The truth-score rubric

Verification evidence has strength, and the score makes it explicit. The score
is the **sum of the signals that actually ran**, capped at 1.00:

| # | Signal | Weight | Granted when |
|---|---|---|---|
| S1 | **Target oracle passed** | 0.50 | The check that proves THIS finding is resolved, passed. By source: `smoke-harness [N]` / `pre-commit` → that specific check now passes; `static-review` → the re-verification (S3) confirms the cited issue is no longer derivable from the code |
| S2 | **No new failures vs. baseline** | 0.20 | The full pre-commit + harness surface ran after the fix and showed no failure that isn't in the Phase 0 baseline (Step 2.3's classification found zero regressions) |
| S3 | **Adversarial re-verification** | 0.15 / 0.08 | 0.15 — an *independent* verifier (subagent that never saw the fix diff) tried to refute the fix and failed; 0.08 — the structured self-refutation pass from `adversarial-verification.md` was run instead. 0 — neither ran |
| S4 | **Test oracle proven red-green** | 0.10 | The proof-test was shown to FAIL with the bug present and PASS with the fix (Step 2.3c). **Granted by construction** for harness/pre-commit findings: the check was red before the fix and green after — that IS a red-green proof. For static findings with no test involvement, granted only if a behavioral oracle was demonstrated (e.g., a repro script that failed before and passes after) |
| S5 | **Minimal, in-scope diff** | 0.05 | The fix touched only files within the finding's blast-radius tier (Step 1.2) and contains no drive-by edits — verify with `git diff --stat` against the tier's file set |

Worked examples:

- **Harness finding, normal path:** S1 0.50 (check green) + S2 0.20 + S3 0.08
  (self-refutation) + S4 0.10 (by construction) + S5 0.05 = **0.93** — clears
  dev (0.90), fails PR (0.95) until S3 is upgraded to independent (→ **1.00**).
- **Critical static finding with a new blind-authored test:** S1 0.50 + S2 0.20
  + S3 0.15 (independent — mandatory for Critical anyway, Step 2.3b) + S4 0.10
  (red-green proven) + S5 0.05 = **1.00**.
- **Static Low fix, no test, self-review only, drive-by formatting included:**
  S1 0.50 + S2 0.20 + S3 0.08 + S4 0 + S5 0 = **0.78** — below every
  threshold. Strengthen: drop the drive-by edits (+0.05), demonstrate a repro
  or behavioral oracle (+0.10) → 0.93.

Scores are not negotiable upward by argument — only by running more
verification. A signal that didn't run scores 0, even when "it obviously would
have passed."

## §2 — Thresholds and environment detection

| Environment | Threshold | Detected when |
|---|---|---|
| dev | 0.90 | default — plain local audit-fix run |
| PR / shared branch | 0.95 | the audit round was change-scoped (PR/diff mode), or the fix lands on a branch with an open PR (`gh pr view --json number` succeeds for the branch) |
| release / main-bound | 0.99 | the user said release / ship / tag / production, or the fixes target the repo's default branch |

Precedence: explicit user instruction > `GREENLOOP_TRUTH_THRESHOLD` env var >
detected environment. When two environments both match (a PR targeting main),
use the higher threshold. Announce the active threshold once, in the Phase 1
plan ("truth threshold: 0.95 — PR-scoped run"), so the user can override before
any fix runs.

The thresholds are calibrated to the rubric, not arbitrary: 0.90 forces at
least a self-refutation pass on every dev fix; 0.95 forces independent
adversarial verification for anything heading to a shared branch; 0.99 means a
release fix needs every signal — independent verification, a proven oracle,
and a clean minimal diff. (The tiering follows claude-flow's dev/staging/prod
0.90/0.95/0.99 convention so the numbers are familiar.)

## §3 — Below threshold: strengthen, then roll back

A sub-threshold score usually means **missing evidence, not a bad fix**. The
response is ordered:

1. **Strengthen** — run the highest-weight missing signal first. Usually that's
   upgrading S3 to an independent verifier or proving S4 red-green. Re-score.
   This is almost always cheaper than rewriting the fix.
2. **Narrow** — if S5 failed, split the drive-by edits out of the fix commit
   (`git add -p`), keep the minimal fix, re-verify, re-score.
3. **Roll back** — if the evidence can't be strengthened (the adversarial check
   returned WEAKENED, the oracle can't be proven, the repro can't be built):
   revert via the standard revert flow, mark the finding
   `open — truth score N.NN < T.TT (<env>), evidence insufficient`, and treat
   it as a failed attempt (interactive: ask the user; headless: defer after the
   attempt limit).

Never do the fourth option — lowering the threshold to fit the score. The
threshold belongs to the destination environment, not to this fix.

### Clean-room re-run (Step 5.0 / pre-commit-verification clean-room mode)

```bash
CR=$(mktemp -d)/cleanroom
git worktree add --detach "$CR" HEAD
(
  cd "$CR" || exit 1
  # install from COMMITTED manifests only — per stack:
  #   Rust: cargo fetch (uses committed Cargo.lock); cargo test
  #   Node: npm ci (NOT npm install — ci respects the committed lockfile exactly)
  #   Python: python -m venv .venv && .venv/bin/pip install -e ".[dev]"
  <run the same verification surface pre-commit-verification ran in-tree>
)
RESULT=$?
git worktree remove --force "$CR"
```

Gotchas:

- **`npm ci`, never `npm install`** — `install` may mutate the lockfile and
  silently "fix" the very drift the clean room exists to catch.
- **Local services** (DBs, daemons) are shared state, not tree state — a test
  that needs one isn't rigged by the worktree, but note it in the report
  ("clean-room ran against the same local Postgres").
- **Env vars do not transfer.** If the in-tree run needed `FOO=1` and the
  clean-room run fails without it, that's a *finding* (undocumented env
  dependency), not a clean-room defect.
- **First run is slower** (cold caches, fresh deps). That cost is bounded by
  running clean-room once per pass, not per fix.
- A clean-room FAIL where in-tree was green reopens the affected findings:
  identify which fix's check failed, drop its S1/S2 accordingly, and report the
  precise delta (the untracked file, the local config, the weakened test).

## §4 — Blind property authoring (the proof-test contract)

When a fix needs a NEW test as its oracle, the test author must not see the
fix. A test written while looking at the patch asserts what the patch *does*;
a test written from the finding asserts what the finding *requires*. Those
diverge exactly when the fix is wrong.

**The author sees only:**
1. the finding text (claim, severity, `file:line`),
2. the relevant spec section (when one exists),
3. the public signature(s) of the function(s) under test.

**The author never sees:** the fix diff, the patched implementation, the fix's
rationale, or any conversation about the fix.

Mechanics:
- **With subagents:** dispatch a test author (read-only context) with exactly
  the three inputs above; it returns the test file content. Same dispatch
  hygiene as the gl-challenger blind contract (`parallel-review.md`).
- **Without subagents:** write the test *before* re-reading the patched code —
  immediately after Step 2.1 (re-verify the finding) is the natural moment,
  since the finding is loaded and the fix doesn't exist yet.

**The freeze rule.** Once the test passes red-green (Step 2.3c), it is frozen
for the remainder of the pass. If the fix later iterates and the frozen test
fails, the fix is wrong — or the spec is, which is a question for the user, not
an edit to the test. The one legitimate exception: the test itself has a bug
(wrong fixture path, typo). Fixing that requires re-proving red-green from
scratch; a "test fix" that skips re-proving is an edit to make the fix pass,
which is what the freeze exists to prevent.

Log: `proof-test: blind-authored (subagent | pre-fix), red-green proven, frozen`.

## §5 — Witness manifest (signed verification record)

Format — `.audit/witness/<UTC timestamp>.json`:

```json
{
  "schema": "greenloop-witness/1",
  "repo": "<origin URL or directory name>",
  "commit": "<full SHA of HEAD verified in the clean room>",
  "timestamp": "<UTC ISO-8601>",
  "skills": {"audit-fix": "0.11.0", "pre-commit-verification": "0.8.0"},
  "clean_room": true,
  "checks": [
    {"name": "unit", "cmd": "cargo test", "result": "pass"},
    {"name": "harness[3] migration idempotency", "result": "pass"}
  ],
  "fixes": [
    {"finding": "3.2", "truth_score": 0.93, "threshold": 0.90, "status": "fixed"}
  ]
}
```

Sign and verify with OpenSSH's built-in Ed25519 signing (no extra tooling —
`ssh-keygen` ships with every macOS/Linux):

```bash
# one-time key generation (with the user's awareness — never silently)
mkdir -p ~/.selran/keys
ssh-keygen -t ed25519 -N "" -f ~/.selran/keys/greenloop-witness -C greenloop-witness

# sign → writes <manifest>.sig next to the manifest
ssh-keygen -Y sign -f ~/.selran/keys/greenloop-witness -n greenloop-witness \
  .audit/witness/2026-06-12T2145Z.json

# verify (the .pub key is shareable; allowed_signers maps identity → key)
echo "greenloop-witness $(cat ~/.selran/keys/greenloop-witness.pub)" > /tmp/allowed_signers
ssh-keygen -Y verify -f /tmp/allowed_signers -I greenloop-witness -n greenloop-witness \
  -s .audit/witness/2026-06-12T2145Z.json.sig < .audit/witness/2026-06-12T2145Z.json
```

Honest scope — what the signature proves and doesn't:

- **Proves:** this manifest existed in exactly this form and was signed by the
  holder of this key. Edits to the record after the fact are detectable. "It
  was green at commit X" becomes checkable instead of anecdotal.
- **Does not prove:** that the checks were comprehensive (coverage declaration's
  job), that the key holder is trustworthy (it's a local key, not a CA), or
  anything about commits after `commit`.

Policy: opt-in. Offer it at the clean-room close; generate the key only with
the user's awareness; skip silently when declined. `.audit/witness/` is
gitignored by default like the rest of `.audit/` — committing a witness is the
user's deliberate choice (e.g., attaching it to a release).
