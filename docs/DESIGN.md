# Selran DevLoop — Design & Build Plan

**Status:** scaffold complete; Phase 1 not started.
**Goal in one sentence:** a reusable, versioned sandbox you point at any repo — it
runs cartographer → app-audit → audit-fix until the oracles are green, on an
isolated branch in a disposable Linux container, and hands back reviewable commits.

---

## 1. Why this exists

The four skills (cartographer, pre-commit-verification, app-audit, audit-fix)
encode a convergent dev methodology, but a human still has to drive them turn by
turn. DevLoop is the engine that runs them autonomously: run the software, find
errors, fix them, repeat — until everything the oracles check is green.

Key insight: **an autonomous loop only converges on errors it can observe with a
pass/fail oracle.** The loop is easy; the oracle is everything. Where nothing turns
red, the agent is blind. So oracle coverage (tests + the smoke/integration
harness) = loop completeness.

## 2. Architecture

```
HOST                          SANDBOX (disposable Linux container)
────                          ────────────────────────────────────
repo (main)                   image: Rust + Node + Postgres + Playwright/WebKit
  │                                  + ~/.claude/skills (the 4) + Agent SDK driver
  ├─ branch: claude/autofix-N        │
  │     └── clone ──────────────────►│  LOOP (Agent SDK):
  │                                   │   cartographer → app-audit (pre-commit+harness)
  │                                   │   → audit-fix → re-audit → repeat
  │                                   │   until: green | stuck | budget
  │   ◄──── push branch + open PR ────┘
  └─ you review the PR → merge (the only human gate)
```

Git is the transfer mechanism, not file copying: the sandbox gets a *branch*, and
returns *commits* (as a PR). Throw the container away after each run; the work
survives as git history.

## 3. Findings that settled the architecture (2026-05)

1. **Claude Desktop ships a Linux micro-VM sandbox** (`claudevm.bundle`: rootfs.img,
   EFI boot, gVisor networking, pre-warmed instance). Proves the sandboxed-Linux
   model is native to this machine. We build a portable Docker image for the
   repeatable artifact; the claudevm is a known fallback execution target.
2. **The backend is probably Linux-bootable but UNVERIFIED.** `backend-rs` deps are
   all cross-platform (tokio, axum, sqlx, reqwest-rustls, rusqlite-bundled, imap,
   lettre). BUT CI builds the backend on `macos-14`, never Linux. `selran-crypto`
   has a macOS-Keychain path under `cfg(target_os = "macos")` — the Linux key path
   needs checking. → **Phase 1 validation gate.**
3. **Native Tauri shell (`src-tauri`) is macOS-only** by nature → Tier 3, deferred.
4. **Frontend already builds on `ubuntu-latest`** in CI → web-layer frontend is
   Linux-clean → Playwright-WebKit headless works in the container.

**Verdict:** clean Linux Docker container for backend + web-frontend; native shell
deferred.

## 4. The repeatable artifact

Three things:
- a versioned **sandbox image** (Docker) with toolchain + skills + driver
- a thin **CLI**: `autoloop <repo> [branch]`
- a per-repo **config**: `.devloop/autoloop.toml` (the only thing that changes per app)

## 5. Phased build plan

### Phase 1 — Sandbox image + Linux validation gate
Build the Dockerfile (Rust, Node, Postgres, Playwright+WebKit, git, skills, Agent
SDK) and the per-repo `autoloop.toml`. **First gate:** prove `backend-rs` builds and
boots in the container; fix/shim `selran-crypto`'s Linux key path (file-based
throwaway key — never a real keychain).
**Done:** backend boots + health responds inside the container for v4.
**Effort:** ~1–2 days.

### Phase 2 — Oracle layer (make errors observable)
Scaffold the harness into the target repo — backend smoke (categories 1,3,7,8) +
Playwright-WebKit frontend specs (5,9), from the templates in
`skills/pre-commit-verification/references/harness/`, customized to the repo's real
routes/screens. This per-repo investment decides how much the loop can catch.
**Done:** `make smoke` runs all applicable categories headless and catches ≥1 known bug.
**Effort:** ~2–3 days.

### Phase 3 — Loop driver (Agent SDK)
The autonomous process: state machine (cartographer→audit→fix→re-audit→repeat),
**stuck-fix policy** (try ≤2 alternative fixes, then mark `deferred — needs human`
and continue), **budget caps** (max iterations / tokens / wall-clock + kill switch),
stop conditions (green | stuck | budget), branch isolation, commit-per-fix, prompt
caching on. Loads the 4 skills as methodology.
**Done:** a full loop runs unattended on v4, fixes ≥1 real finding, commits, stops with a report.
**Effort:** ~3–4 days.

### Phase 4 — Run wrapper + PR review gate
`autoloop run <repo>`: cut branch, clone into sandbox, run loop, push branch, open a
PR with a run report (AUDIT_LOG delta + commit log + harness before/after). You
review the PR; you merge. Nothing auto-touches main.
**Done:** end-to-end on v4 → PR with reviewable commits + report.
**Effort:** ~1–2 days.

### Phase 5 — Prove repeatability
Run the whole thing on a second repo (librarian or Cortex) changing only
`autoloop.toml` + a harness scaffold. Write the "onboard a new repo" doc.
**Done:** a second app runs through the loop with config-only changes.
**Effort:** ~1 day.

### Phase 6 — (Deferred) macOS GUI tier
macOS VM (`tart`) or host runner for the native `.app` + real WKWebView (harness
categories 5/9 against the real shell). Build only when web-layer coverage is
exhausted and native-shell bugs dominate.

## 6. Sequencing & risks

**Order:** 1 → 2 → 3 → 4 → 5 (2 and 3 can overlap). 6 deferred.
**Rough effort to repeatable v1 (backend + web-frontend):** ~8–12 focused days.

**Risks:**
- Linux-boot unverified — Phase 1 gate; may surface a `selran-crypto` Linux gap.
- Oracle coverage = loop completeness; under-investing in Phase 2 makes the loop
  report green while real bugs hide.
- Stuck-fix policy is the crux of safe autonomy (≤2 alts, then defer).
- Never against main; throwaway secrets only; per-fix verify is the blast-radius
  containment.

## 7. First concrete step

Phase 1 validation gate: attempt to build and boot `backend-rs` in a Linux
container, and check whether `selran-crypto` compiles on Linux. That single
experiment de-risks the whole plan.
