# Phase 1 — Findings

**Date:** 2026-05-20
**Goal:** prove `backend-rs` builds and boots on Linux in a container (the gate that
de-risks the whole sandbox approach).

## Status: ✅ PASS

The v4 backend builds, links, migrates, boots, and answers `/api/health` inside the
disposable Linux container:

```
=== [4/4] boot + health ===
{"status":"ok","version":"4.0.0","phase":"2 — Identity + OAuth"}
PASS: backend builds and boots on Linux.
```

| Sub-step | Status |
|---|---|
| Sandbox `Dockerfile` | ✅ done |
| `validate-linux.sh` (staged gate, cached, log-capturing) | ✅ done |
| `selran-crypto` compiles on Linux (the macOS/Linux keychain split) | ✅ confirmed on real Linux |
| `backend-rs` compiles + links on Linux | ✅ confirmed |
| backend boots + `/api/health` responds | ✅ confirmed |

## The core risk is fully resolved

`selran-crypto` is properly cross-platform (`cfg(target_os)`: macOS →
security-framework, Linux → keyring/sync-secret-service, Windows → windows-native,
+ fallback). It compiled and ran on real Linux. The two Linux requirements are both
handled in the image:
1. **Build:** `libdbus-1-dev` + `pkg-config` (so `libdbus-sys` builds).
2. **Runtime:** a secret-service daemon — `validate-linux.sh` starts a throwaway
   `dbus-run-session` + `gnome-keyring-daemon --unlock` (empty password, never a
   real secret).

## Boot blockers cleared (one per iteration)

The staged gate + backend-log capture pinpointed each, in order:

| # | Failure | Fix |
|---|---|---|
| 1 | `DATABASE_URL is not set` | set it in the boot stage |
| 2 | health never connected — `BACKEND_RS_BIND` defaults to `127.0.0.1:0` (random port) | pin `127.0.0.1:8765` |
| 3 | `password authentication failed for user "postgres"` | `pg_hba.conf` is first-match-wins; rewrite auth methods to `trust` (throwaway DB) |
| 4 | `migration error: type "vector" does not exist` | build + install **pgvector** (v0.8.0) into the image |

## v4 finding to carry into the audit (NOT a sandbox issue)

**Migration 1 hard-requires the `vector` type, contradicting the §14.3 graceful-
degradation claim.** At boot v4 logs:

```
INFO  pgvector unavailable: extension "vector" is not available — vector features
      will be runtime-disabled (§14.3)
fatal: migration error: while executing migration 1: type "vector" does not exist
```

So v4 *says* it will runtime-disable vector features when pgvector is absent, but the
migration then fails hard on the `vector` type — meaning on any Postgres without
pgvector, v4 cannot boot at all. The graceful-degradation path and the migration
disagree. This is a real spec-vs-reality finding for a later app-audit run
(Operational readiness / Spec compliance). The sandbox sidesteps it by providing
pgvector; the inconsistency in v4 remains.

## How to run the gate

```bash
./sandbox/validate-linux.sh /Users/aidin/NeutronDev/selran-mail-v4
```

Requires a container runtime (docker/podman). Build cache persists in the
`devloop-cargo-registry` and `devloop-cargo-target` volumes, so re-runs after the
first are incremental and fast.

## Notes

- The cross-check left a `target/aarch64-unknown-linux-gnu/` dir under
  `selran-mail-v4` and added the `aarch64-unknown-linux-gnu` rustup target. Harmless;
  removable with `cargo clean --target aarch64-unknown-linux-gnu`.
- The boot uses a throwaway Postgres (trust auth) and a throwaway keychain. No real
  secrets enter the sandbox.
