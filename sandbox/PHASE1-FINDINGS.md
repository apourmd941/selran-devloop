# Phase 1 — Findings

**Date:** 2026-05-20
**Goal:** prove `backend-rs` builds and boots on Linux in a container (the gate that
de-risks the whole sandbox approach).

## Status: build tooling done; executable gate blocked on a container runtime

| Sub-step | Status |
|---|---|
| Sandbox `Dockerfile` written | ✅ done |
| `validate-linux.sh` (staged gate) written | ✅ done |
| Core risk investigated (`selran-crypto` macOS/Linux split) | ✅ resolved by inspection + cross-check |
| Actually build + boot in a Linux container | ⛔ blocked — **no container runtime installed** |

No `docker`, `podman`, `colima`, `orbstack`, `lima`, `nerdctl`, or `finch` is present
on the host, so the boot+health gate cannot run yet. The Dockerfile and validation
script are ready for the moment a runtime exists.

## The core risk is resolved (by inspection + cross-compile check)

The flagged risk was that `selran-crypto`'s macOS-Keychain code (`cfg(target_os =
"macos")` → `security-framework`) might leave a Linux gap that blocks the backend on
Linux. It does not:

- `selran-crypto/src/keychain/mod.rs` dispatches by `cfg(target_os)`:
  - **macOS** → `security-framework` (`keychain/macos.rs`)
  - **Linux / Windows** → `keyring` 3.x (`keychain/keyring_backend.rs`)
  - plus a fallback for other OSes
- A cross-compile check from macOS (`cargo check -p selran-crypto --target
  aarch64-unknown-linux-gnu`) compiled all the pure-Rust crypto (hkdf, aes, argon2,
  aes-gcm, …) cleanly. It stopped only at **`libdbus-sys`**, the C D-Bus binding
  pulled in by `keyring`'s `sync-secret-service` feature — and that stop is a
  *cross-compilation* limitation (pkg-config can't cross from macOS without a Linux
  sysroot), **not** a code problem.

**Conclusion:** the Rust is Linux-clean. The Linux keychain path has two real
Linux requirements, both now handled in the Dockerfile:

1. **Build:** `libdbus-1-dev` + `pkg-config` (so `libdbus-sys` compiles). Added.
2. **Runtime:** a **secret-service daemon** (D-Bus). A headless container has none,
   so the app would compile but fail at boot reaching the keychain. The Dockerfile
   installs `dbus` + `gnome-keyring`; `validate-linux.sh` starts a throwaway
   `dbus-run-session` + `gnome-keyring-daemon --unlock` (empty password, never a
   real secret) before launching the backend.

   *Longer-term option:* add a `file`-keystore feature to `selran-crypto` for
   sandbox/CI use (matches the `keystore = "file"` intent in
   `templates/autoloop.toml.example`). Cleaner than running a keyring daemon, but
   it's a code change to the target — deferred unless the daemon approach proves flaky.

## What "complete Phase 1" still needs

A container runtime. To finish the gate:

```bash
brew install colima docker && colima start    # lightest option
./sandbox/validate-linux.sh /Users/aidin/NeutronDev/selran-mail-v4
```

Expected first real failure modes to watch (now that the crypto risk is cleared):
- Postgres bring-up inside the container (the migration smoke needs a live DB)
- the backend's launch command + health URL (wire from the repo's `autoloop.toml`)
- the secret-service handshake at boot

## Other notes

- The cross-check left a `target/aarch64-unknown-linux-gnu/` dir under
  `selran-mail-v4` and added the rustup target. Harmless; can be removed with
  `cargo clean --target aarch64-unknown-linux-gnu`.
