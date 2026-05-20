# sandbox/ — Phase 1

The reproducible Linux container image: Rust, Node, Postgres, Playwright+WebKit,
git, the four skills, and the Agent SDK loop driver.

**Not built yet.** Phase 1's first task is the Linux validation gate — prove
`backend-rs` builds and boots in this container and that `selran-crypto` compiles
on Linux (it has a macOS-Keychain path under `cfg(target_os = "macos")`; the Linux
path needs a file-based throwaway key shim).

See `docs/DESIGN.md` §5 Phase 1.
