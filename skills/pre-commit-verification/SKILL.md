---
name: pre-commit-verification
version: 0.9.0
description: Use this skill whenever the user asks to verify, test, check, validate, or confirm their repo before committing or pushing — including requests like "do a pre commit verification", "run local tests before push", "deep local verification", "fix everything and test it", "make sure this is ready", or "run the full verification pass". Covers stack-aware test discovery, unit/integration/e2e tests, smoke tests, lint checks, type checks, builds, and a runtime smoke/integration harness (binary-launch, migration idempotency, provider mocks, headless webview + browser verification for web UIs, env probe). Supports a tamper-proof clean-room mode (re-run in a fresh worktree of HEAD so uncommitted state can't rig the verdict), an Ed25519-signed witness manifest for tamper-evident green results, and per-check reliability tracking across runs (pass³) that exposes flaky checks instead of retrying them green. Do NOT use for a single narrow test unless explicitly requested.
---

# Pre Commit Verification

## Overview

Run the deepest practical local verification surface for the current repo, fix failures, rerun the smallest useful checks first, then confirm the broad local state before commit.

This skill runs **two layers**:
1. **The repo's existing checks** — whatever tests, lint, type-check, and build the repo already defines (stack-aware discovery).
2. **The runtime smoke/integration harness** — a set of launch/integration tests that catch the failure classes unit tests structurally cannot (binary won't boot, CORS missing at runtime, migrations not idempotent, webview quirks, missing env under launchd, external-API contract drift). See "Smoke/Integration Harness" below.

The harness is what closes the gap where "all tests pass but the app fails when actually launched." Unit tests run in a sanitized context (mocked DB, mocked providers, no real binary, no real webview) and pass while the integrated, launched system fails. The harness exercises the real launched system.

## When To Use

Use this skill when the user asks to:
- do a pre commit verification
- run the full local verification pass
- do a deep local test run
- fix local failures before commit
- make sure a repo is ready before push
- run the repo's real local checks, not just one test command
- verify everything works before pushing

Do not use this skill for a single narrow test unless the user clearly wants only that narrow check.

This skill is also invoked automatically by **app-audit** (Phase 0, as the clean-baseline gate) and **audit-fix** (Phase 0 preflight, and after every fix). When invoked by app-audit, the structured results — including per-category harness outcomes — are folded into `AUDIT_LOG.md` (see "Structured result reporting" below).

## Core Principle

Do not assume one fixed gate. Inspect the repo and run the broadest practical local verification surface that matches its stack and conventions.

## Verification Surface To Consider

Inspect the repo and include the applicable categories:
- unit tests
- integration tests
- end-to-end tests when practical locally
- acceptance tests mapped in `.audit/acceptance-map.md` when it exists (the spec→test mapping app-audit maintains) — run the mapped tests and report `acceptance: N mapped, M run, K UNMAPPED`; grading the gaps is app-audit's job, running the tests is this skill's
- smoke tests (and the runtime harness below)
- lint checks
- type checks
- build checks
- format checks
- security or dependency checks if they are part of the repo workflow
- database or migration checks if schema changes are involved
- runtime or service startup checks
- API contract checks
- UI behavior checks
- CLI or script validation
- model or ML inference checks
- light performance sanity checks when regressions are suspected
- cross-platform sanity checks when the repo explicitly targets multiple OSes
- git and repo hygiene checks

## Workflow

1. Start in the current repo and inspect:
   - `git status --short`
   - key docs and manifests such as `README.md`, `AGENTS.md`, `pyproject.toml`, `package.json`, `Makefile`, `justfile`, CI config, and test config files
2. Infer the repo's actual local verification surface from those files.
3. **Check whether the smoke/integration harness is scaffolded.** Look for the harness directory the repo uses (e.g., `tests/smoke/`, `smoke/`, or whatever the project adopted). If the repo is a runnable app and the harness is missing, offer to scaffold it (see "Scaffolding the harness").
4. If services are currently running and can interfere with tests, stop them first.
5. Run the broad local verification set — existing checks **plus** the harness.
6. If something fails:
   - fix the real issue
   - rerun the smallest relevant check first
   - then rerun the broader verification set
7. Finish with a clear readiness summary for commit, in the structured format below.

## Default Checks By Stack

### Python-heavy repos
```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/ -q --no-header
./.venv/bin/python -m ruff check src tests
./.venv/bin/python -m mypy src
```
Adjust `PYTHONPATH`, package path, and test scope to the repo layout.

### Frontend repos
```bash
npm run build
npm run test
npm run lint
```
Use the commands the repo actually defines rather than forcing a generic pattern.

### Full-stack and desktop (Tauri/Electron) repos
Combine backend and frontend verification, then run the smoke/integration harness — for a desktop app, that's the layer most likely to catch real failures.

## Smoke/Integration Harness

The harness is a set of runnable tests that exercise the **launched** system. It lives in the project (scaffolded once, then owned and customized by the project), and pre-commit-verification runs it as part of the verification surface. The pattern mirrors cartographer's `_build.py`: the skill ships templates in `references/harness/`, they're copied into the project once, customized per project, then run on every verification pass.

### The categories

Each template targets a class of runtime failure that static analysis and unit tests miss. The numbering matches the failure taxonomy these were designed against:

| # | Failure class | Template | What it does |
|---|---|---|---|
| 1+4 | runtime + build-graph | `smoke_http_health.rs` | Launch the binary, fetch `/api/health` with an `Origin` header, assert 200 + CORS header present + a non-empty startup log line |
| 2 | context-dependent | `dev_prod_matrix.sh` | Run the smoke suite under **both** dev and prod-bundled launch contexts |
| 3 | stateful DB | `migration_idempotency.sh` | Fresh DB → run migrations → run them **again** → assert idempotent (second run is a clean no-op) |
| 5 | browser quirks | `webview_e2e.spec.ts` | Headless automation that drives the actual `.app` webview (Playwright-style), not a mocked DOM |
| 6 | missing layers | (static — see note) | Required middleware for cross-origin webview. This one is **not a runtime test** — it's a static checklist item owned by app-audit (Category: security / external integrations). The harness verifies behavior; app-audit verifies the layer is *present*. |
| 7 | launch env | `env_probe.sh` | Launch under a stripped environment (`env -i PATH=...`, launchd-style) to catch "works in my shell, fails when launched by the OS" |
| 8 | external APIs | `provider_mock_test.rs` | Fixture-based provider tests with wiremock/httpmock — pin external-API contracts so provider drift is caught locally |
| 9 | UX | `onboarding_clickthrough.spec.ts` | Click-through automation of onboarding-style flows |

Category 6 is intentionally not a runtime test. It's a structural fact ("is the CORS middleware registered?") that app-audit checks statically. The harness's category-1 test catches the *behavioral* failure (wrong header at runtime); app-audit's checklist catches the *structural* absence. Both are needed — presence ≠ correct behavior.

**Web apps, not just desktop.** Categories 5 and 9 apply to any web frontend, not only desktop webviews: point Playwright (or the available browser/preview tooling) at the dev server and drive the **actual rendered page** — load the route, assert the critical element exists, exercise the key interaction, check the console for errors. The `webview_e2e.spec.ts` template works as the starting point (swap the `.app` target for the dev-server URL). When the change under verification touches UI code, this browser layer is **required, not optional** — a component can compile, pass unit tests, and still render blank; only a real browser catches that class.

### Scaffolding the harness

When the repo is a runnable app and the harness isn't present:

1. Tell the user what's missing and offer to scaffold:
   > "This repo has no runtime smoke harness. The unit tests pass but won't catch launch/integration failures (binary boot, CORS at runtime, migration idempotency, webview behavior, env-under-launchd, provider drift). I can scaffold a starter harness from templates — you'll customize the project-specific bits (binary name, health route, DB URL). Scaffold it?"
2. On approval, copy the relevant templates from `references/harness/` into the project's chosen location (default `tests/smoke/` for a Rust backend, `e2e/` for webview specs). Only scaffold categories that apply to the stack.
3. Each template has clearly marked customization points (`# CUSTOMIZE:` comments). Fill in what's known from the repo (binary path, health endpoint, migration command); leave a TODO for what isn't.
4. Wire the harness into the repo's verification entry point — a `make smoke` target, an npm script, or a `cargo test --test smoke_*` pattern — so it's discoverable on future runs and the project owns it.

Do not re-scaffold if the harness already exists. Treat the project's copies as authoritative (the templates are starting points, not a source of truth to overwrite).

### Running the harness

- Run it as part of step 5 of the workflow, after the existing checks pass (no point launching a binary that didn't build).
- Each category runs independently and reports its own pass/fail. A failure in one category does not skip the others — run them all, report all.
- Harness tests are heavier than unit tests (they launch processes, spin up DBs, drive webviews). Keep them focused; don't expand into long manual QA.

### Launching a server safely (CRITICAL — avoid the background-process deadlock)

When you launch a server in the background to probe it (HTTP health, webview, etc.),
**never** end with bare `wait` and **never** rely on `%`-job control. A non-interactive
shell has job control off, so `kill %1` silently does nothing, and `wait` then blocks
**forever** on a server that never exits — freezing the whole verification (and, under
the DevLoop driver, the entire loop). This is the single most common way a smoke check
hangs. Always: capture the PID, bound the whole thing with `timeout`, and kill the PID
explicitly (never `kill %1; wait`).

Safe, stack-agnostic pattern:

```bash
# 1) launch, capture the real PID, redirect output to a file (not the tool's pipe)
<server-launch-cmd> > /tmp/smoke.log 2>&1 &
SRV=$!
# 2) wait for readiness with a BOUNDED poll (never an unbounded wait)
for i in $(seq 1 30); do
  curl -fsS "$HEALTH_URL" >/dev/null 2>&1 && break
  sleep 1
done
# 3) do the probe(s)
curl -sS -i "$HEALTH_URL" | head -20
# 4) ALWAYS tear down by PID, then reap only that PID (never bare `wait`)
kill "$SRV" 2>/dev/null || true
wait "$SRV" 2>/dev/null || true   # reaps ONLY $SRV — safe; bare `wait` is not
```

Belt-and-suspenders: wrap the launch in `timeout 60 bash -c '…'` so even a botched
teardown self-terminates. If a server ignores SIGTERM, escalate (`kill -9 "$SRV"`).
Prefer an in-process test client (e.g. FastAPI `TestClient`, axum test server) over a
bound network server when you only need to hit a route — it can't leak a process at all.

## Reliability tracking (pass³ — catching flaky checks)

A check that passes *this run* and a check that passes *reliably* are different
claims, and flaky tests are how false confidence gets institutionalized. Track
per-check results across runs in `.audit/check-history.json` (append one entry
per run: check name, pass/fail, HEAD SHA, timestamp; keep the last ~20 runs):

- **Stability grade:** a check is **stable** when it has passed 3 consecutive
  runs (pass³). Report below-grade checks in the summary:
  `reliability: 14/15 checks pass³-stable; harness[5] webview e2e flipped 2× in last 5 runs`.
- **Flaky candidate:** a check that changed verdict between runs at the **same
  HEAD** (or with no commits touching its blast radius in between) is flaky by
  definition — the code didn't change, the verdict did. Surface it so app-audit
  can grade it as a finding (Category 9 — a flaky test is missing coverage
  wearing a green badge). Don't silently retry-until-green; that's the
  anti-pattern this exists to catch.
- History is advisory, never blocking: a red run still reports red regardless
  of past stability. Missing/corrupt history file → start fresh, skip silently.

## Clean-room mode (tamper-proof re-run)

A verification run in the working tree answers "is this *tree* green?" — which
includes every uncommitted file, edited test, and local-only config. That
verdict can be rigged, accidentally or otherwise: a helper file that was never
`git add`-ed, a test weakened during debugging, a `.env` that exists only on
this machine. Clean-room mode answers the question that actually matters before
a push or release: **"is what's committed green?"**

Run the same verification surface in a **fresh worktree of HEAD**:

```bash
CR=$(mktemp -d)/cleanroom
git worktree add --detach "$CR" HEAD
# install deps from committed manifests only, then run the same checks there
( cd "$CR" && <install + run the verification surface> )
RESULT=$?
git worktree remove --force "$CR"
```

- The worktree contains **committed state only** — no uncommitted edits, no
  untracked files, no local artifacts. Dependencies install from the committed
  lockfiles; build caches may make the first clean-room run slower. That cost
  is the point.
- **Compare against the in-tree result.** Same outcome → the verdict is honest.
  **Green in-tree but red in the clean room** → something uncommitted is
  load-bearing. Name the delta precisely (`tests pass in tree, fail at HEAD:
  src/config_local.py is untracked`) — that diagnosis is the entire value.
- **When to run it:** once per pass, not per fix — on "make sure this is ready
  before push/release" requests, and as audit-fix's Phase 5 close gate. Skip it
  for quick mid-development checks; it's a gate, not a loop step.
- Full recipe with per-stack install notes and gotchas: audit-fix's
  `references/verification-depth.md` §3.

## Witness manifest (signed verification record)

After a clean-room pass goes green, the result can be recorded as a
**tamper-evident witness** instead of just a log line: write
`.audit/witness/<timestamp>.json` containing the commit SHA, the per-check and
per-harness-category results, truth scores (when invoked by audit-fix), and the
skill versions — then sign it with a local Ed25519 key:

```bash
# one-time: generate the witness key (no passphrase; it signs, it's not a secret store)
ssh-keygen -t ed25519 -N "" -f ~/.selran/keys/greenloop-witness -C greenloop-witness
# sign
ssh-keygen -Y sign -f ~/.selran/keys/greenloop-witness -n greenloop-witness \
  .audit/witness/<timestamp>.json
# anyone with the .pub can verify
ssh-keygen -Y verify -f allowed_signers -I greenloop-witness -n greenloop-witness \
  -s .audit/witness/<timestamp>.json.sig < .audit/witness/<timestamp>.json
```

What it proves: this manifest existed in this exact form and was signed by this
key — so a later claim of "it was green at commit X" is checkable, and silent
edits to the record are detectable. What it does NOT prove: that the checks
themselves were comprehensive (that's the coverage declaration's job). Offer it,
don't force it — generate the key only with the user's awareness, and skip
silently when declined. Manifest format: audit-fix's
`references/verification-depth.md` §5.

## Structured result reporting

Always report results in this structure, so app-audit can capture them into `AUDIT_LOG.md` and audit-fix can act on failures:

```
Pre-commit verification — <commit-or-HEAD>, <timestamp>
Final result: PASSED | PASSED-AFTER-FIXES | RED

Existing checks:
- unit/integration: <cmd> → <N passed / M failed>
- lint: <cmd> → clean | <issues>
- typecheck: <cmd> → clean | <issues>
- build: <cmd> → success | failure
- format: <cmd> → clean | <issues>
- acceptance (when .audit/acceptance-map.md exists): <N mapped, M run, K UNMAPPED> → <passed/failed>

Smoke/integration harness:
- [1+4] HTTP health smoke      → PASS | FAIL: <detail> | SKIPPED: <why>
- [2]   dev/prod matrix        → PASS | FAIL (dev) | FAIL (prod-bundled): <detail>
- [3]   migration idempotency  → PASS | FAIL: <detail>
- [5]   webview e2e            → PASS | FAIL: <detail> | SKIPPED: <why>
- [7]   launch-env probe       → PASS | FAIL: <detail>
- [8]   provider mocks         → PASS | FAIL: <detail>
- [9]   onboarding clickthrough → PASS | FAIL: <detail>

Auto-fixed this run: <list, or none>
Still red (could not auto-fix): <list, or none>
Repo state: clean | dirty (<paths>)
Clean-room re-run: PASS (worktree @ <sha>) | FAIL: <delta vs in-tree> | not run (<why>)
Witness: .audit/witness/<ts>.json (signed) | not written
Could not verify locally: <list, or none>
```

When a harness category FAILS and you cannot auto-fix it, report it with enough location detail (test name, the file/route/migration involved) that it can become a finding. app-audit converts these into severity-graded findings in `AUDIT_LOG.md`; audit-fix then re-runs that specific check to re-verify before and after fixing.

**Known-failure baselines.** This skill reports results; it does not decide what a failure means for the caller. When invoked by audit-fix mid-remediation, some checks are *expected* to fail (they correspond to findings not yet fixed) — audit-fix compares the per-check results against its Phase 0 baseline and only treats *new* failures as regressions. So: always report every check's result faithfully, including expected failures, and never summarize a run as simply "RED" without the per-check breakdown — the breakdown is what makes baseline comparison possible.

## Failure Handling

### Prefer narrow reruns before broad reruns
After a fix, rerun the smallest relevant test, check, build, or smoke step first. Then rerun the wider suite.

### Running services can pollute results
If local workers, dev servers, or background tasks are causing lock contention, generated churn, or CPU pressure, stop them before the deep verification pass when practical.

### Generated artifacts
Do not treat generated files as meaningful product changes unless the repo intentionally tracks them.

## Guardrails

- Do not revert unrelated user changes.
- Prefer fixing the real issue instead of weakening or skipping tests — including harness tests. A harness test that's flaky should be made deterministic, not deleted.
- **Any NEW test written during this pass must be proven able to fail** before it counts as verification: break the asserted behavior once (or run against the pre-fix state), watch the test go red, restore. A test that passes regardless is false confidence, not coverage. (Full red-green protocol: audit-fix's `references/adversarial-verification.md`.)
- Match the repo's actual conventions instead of forcing a repo-specific workflow everywhere.
- Never scaffold the harness into a repo that already has it; treat the project's copies as authoritative.
- Treat this as pre-commit local verification first; commit, push, and GitHub monitoring come after this unless the user explicitly asks for the whole chain.

## Reference files

- `references/harness/README.md` — manifest of the harness templates, scaffolding guidance, customization points, and how each category maps to the failure taxonomy. Read before scaffolding.
- `references/harness/*` — the per-category test templates. Copy into the project on scaffold; customize the marked points.
- audit-fix's `references/verification-depth.md` — clean-room worktree recipe with per-stack install notes (§3) and the witness manifest format + sign/verify recipes (§5).
