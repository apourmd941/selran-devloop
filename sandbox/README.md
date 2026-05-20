# sandbox/ — Phase 1 (in progress)

The reproducible Linux container image: Rust, Node, Postgres, Playwright+WebKit,
git, and the four skills. The Agent SDK loop driver mounts/clones the target
repo's branch into `/work` at runtime (Phase 3).

## Files

- `Dockerfile` — the sandbox image.
- `validate-linux.sh` — the staged validation gate (check crypto → check backend →
  build → boot + health). Needs a container runtime.
- `PHASE1-FINDINGS.md` — what the validation surfaced.

## Status

Build tooling done. The **core risk is resolved**: `selran-crypto` is properly
cross-platform (macOS → security-framework, Linux → keyring/secret-service); a
cross-compile check confirmed the Rust compiles for Linux. The Linux keychain path
needs `libdbus-1-dev` (build, now in the Dockerfile) + a secret-service daemon
(runtime, started by `validate-linux.sh`).

The **executable gate (build + boot in a container) is blocked** — no container
runtime is installed on the host. To finish:

```bash
brew install colima docker && colima start
./sandbox/validate-linux.sh /Users/aidin/NeutronDev/selran-mail-v4
```

See `PHASE1-FINDINGS.md` and `docs/DESIGN.md` §5 Phase 1.
