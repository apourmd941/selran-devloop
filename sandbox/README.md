# sandbox/ — Phase 1 (in progress)

The reproducible Linux container image: Rust, Node, Postgres, Playwright+WebKit,
git, and the four skills. The Agent SDK loop driver mounts/clones the target
repo's branch into `/work` at runtime (Phase 3).

## Files

- `Dockerfile` — the sandbox image.
- `validate-linux.sh` — the staged validation gate (check crypto → check backend →
  build → boot + health). Needs a container runtime.
- `PHASE1-FINDINGS.md` — what the validation surfaced.

## Status: ✅ PASS

The v4 backend builds, links, migrates, boots, and answers `/api/health` inside the
container:

```
{"status":"ok","version":"4.0.0","phase":"2 — Identity + OAuth"}
PASS: backend builds and boots on Linux.
```

Run it:

```bash
./sandbox/validate-linux.sh /path/to/your-rust-app
```

Four boot blockers were cleared along the way (DATABASE_URL, random bind port,
pg_hba auth, pgvector) — see `PHASE1-FINDINGS.md` for the full table and the one v4
finding (migration 1 hard-requires the `vector` type despite the §14.3
graceful-degradation claim) to carry into a later audit.
