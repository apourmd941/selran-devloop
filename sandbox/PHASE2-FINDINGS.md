# Phase 2 — Findings (oracle layer)

**Date:** 2026-05-20
**Goal:** make the smoke/integration harness real for v4 — a single `make smoke`
that runs the runtime categories headless, so the loop has oracles to converge on.

## Status: backend oracle layer ✅ verified; frontend e2e scaffolded (Tauri caveat)

Backend smoke runs green in the Linux sandbox via `make smoke`:

```
== [1+4,6] http smoke ==        3 passed (health + CORS preflight + cross-origin header)
== [3] migration idempotency == 1 passed (against a real pgvector Postgres)
== [5,9] frontend e2e ==        SKIP (scaffolded; see Tauri caveat below)
SMOKE: PASS
```

## Built on what v4 already had (no duplication)

v4 already shipped good backend smoke tests (written for audit findings R6.1 / R3.4):
- `backend-rs/tests/http_smoke.rs` — router health (200) + CORS preflight + cross-
  origin allow-origin header (categories 1+4 and 6). Runs via tower `oneshot` — no
  port bind, no DB — so it runs anywhere `cargo test` runs.
- `backend-rs/tests/migrations.rs` — fresh DB → migrate → migrate again → assert
  idempotent, plus the `mail._sqlx_migrations` shadow-table check (category 3). It
  self-skips unless `SELRAN_TEST_DATABASE_URL` is set.

Phase 2 did NOT rewrite these. It made them **runnable as one suite** and **actually
ran the gated migration test against a real DB**:

| Added (v4, on a branch) | Purpose |
|---|---|
| `Makefile` + `scripts/smoke.sh` | single `make smoke` entry the loop/sandbox calls; each category self-skips when prereqs are absent |
| `frontend/playwright.config.ts`, `e2e/{smoke,onboarding}.spec.ts`, `e2e/_tauri-mock.ts` | frontend e2e scaffold (categories 5, 9) |
| `frontend/package.json` | `@playwright/test` devDep + `test:e2e` script |

| Added (devloop) | Purpose |
|---|---|
| `sandbox/run-smoke.sh` | Phase 2 sandbox runner — Postgres+pgvector+secret-service, then `make smoke` |

## What the migration oracle proves

Run #1 of the smoke surface caught the **colima OOM** (linker `ld` killed during
`http_smoke` link at the 2 GB default) — fixed by `colima start --memory 8`. The
migration test itself **passed against a real pgvector Postgres**, exercising the
exact regression guard for the migration bugs that surfaced earlier this session
(non-idempotent `CREATE SCHEMA mail`, the `mail._sqlx_migrations` search_path
shadow). That is the runtime oracle working as intended.

## Honest boundary: frontend e2e (categories 5, 9)

Scaffolded, not yet runnable end-to-end, because v4's frontend is a **Tauri** app
that expects the `window.__TAURI__` bridge. Plain Playwright-WebKit provides the
WebKit *engine* (good for CSP/CSS/API-quirk coverage) but **not** the Tauri runtime,
so the app errors on boot without a mock.

- `e2e/_tauri-mock.ts` injects a minimal `__TAURI__` stub so the web layer can
  render headless. It returns benign defaults; it must be fleshed out per the
  commands v4 invokes on each tested path.
- True native-shell fidelity (real WKWebView + Tauri IPC) is **DevLoop Tier 3**
  (macOS + tauri-driver), deferred.

So categories 5/9 are wired into `make smoke` and will run once (a) the Tauri mock
covers the boot path or (b) Tier 3 lands. Backend categories (1+4, 6, 3) are fully
verified now.

## How to run

```bash
# In the sandbox (backend categories, real DB):
./sandbox/run-smoke.sh /Users/aidin/NeutronDev/selran-mail-v4

# Locally in v4 (self-skips what isn't set up):
cd /Users/aidin/NeutronDev/selran-mail-v4 && make smoke
```

## Carry-forward

- Frontend e2e needs the Tauri mock fleshed out (or Tier 3). Follow-on.
- The colima sandbox needs ≥ ~6–8 GB RAM or the Rust test link OOMs. Documented.
