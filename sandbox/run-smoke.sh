#!/usr/bin/env bash
# Phase 2 — run the target repo's smoke surface in the Linux sandbox.
#
# Builds the sandbox image, stands up Postgres (+pgvector) and a headless
# secret-service, then runs the BACKEND smoke surface against a real DB:
#   - cargo test --test http_smoke   (router health + CORS; no DB needed)
#   - cargo test --test migrations    (idempotency; SELRAN_TEST_DATABASE_URL set here)
#
# Frontend e2e (Playwright-WebKit) is wired into the repo's `make smoke` but is
# NOT run here — v4's frontend needs a Tauri-bridge mock to render headless (see
# frontend/e2e/_tauri-mock.ts); fleshing that out is follow-on work, and true
# native-shell fidelity is DevLoop Tier 3 (macOS + tauri-driver).
#
# Usage:  ./sandbox/run-smoke.sh /path/to/target-repo
# Exit 0 = backend smoke passed.

set -uo pipefail

TARGET_REPO="${1:?usage: run-smoke.sh /path/to/target-repo}"
IMAGE="selran-devloop:latest"
RUNTIME="$(command -v docker || command -v podman || true)"
[[ -z "$RUNTIME" ]] && { echo "FAIL: no container runtime (docker/podman)." >&2; exit 2; }

SANDBOX_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SANDBOX_DIR/.." && pwd)"
echo "[run-smoke] building image..."
"$RUNTIME" build -t "$IMAGE" -f "$SANDBOX_DIR/Dockerfile" "$REPO_ROOT" || { echo "FAIL: image build" >&2; exit 1; }

"$RUNTIME" run --rm \
  -v "$TARGET_REPO":/src:ro \
  -v devloop-cargo-registry:/root/.cargo/registry \
  -v devloop-cargo-target:/cargo-target \
  -e CARGO_TARGET_DIR=/cargo-target \
  "$IMAGE" bash -euo pipefail -c '
    echo "=== copy source (excluding target/.git/.claude/node_modules) ==="
    mkdir -p /work
    ( cd /src && tar -cf - \
        --exclude="./target" --exclude="./.git" --exclude="./.claude" \
        --exclude="./node_modules" --exclude="*/node_modules" . ) \
      | ( cd /work && tar -xf - )
    cd /work

    echo "=== Postgres up (trust auth) + pgvector test DB ==="
    service postgresql start || pg_ctlcluster "$(ls /etc/postgresql)" main start || true
    for n in $(seq 1 20); do pg_isready -h 127.0.0.1 -p 5432 && break; sleep 0.5; done
    PGHBA="$(ls /etc/postgresql/*/main/pg_hba.conf | head -1)"
    sed -i "s/scram-sha-256/trust/g; s/md5/trust/g; s/peer/trust/g" "$PGHBA"
    service postgresql restart || pg_ctlcluster "$(ls /etc/postgresql)" main restart || true
    for n in $(seq 1 20); do pg_isready -h 127.0.0.1 -p 5432 && break; sleep 0.5; done
    su postgres -c "createdb selran_test" 2>/dev/null || true

    # The migration test connects here and runs run_migrations twice. pgvector is
    # installed in the image; migration 0001 creates the extension itself.
    export SELRAN_TEST_DATABASE_URL="postgres://postgres@127.0.0.1:5432/selran_test"

    echo "=== make smoke (backend categories) ==="
    # Run the backend smoke directly (http_smoke needs no DB; migrations uses the
    # test DB above). The frontend e2e step self-skips (no node_modules here).
    bash scripts/smoke.sh
  '
RC=$?
[[ $RC -eq 0 ]] && echo "PASS: backend smoke passed in the sandbox." \
                || echo "FAIL: backend smoke failed (rc=$RC)." >&2
exit $RC
