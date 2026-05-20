#!/usr/bin/env bash
# Phase 1 validation gate — does the target's backend build and boot on Linux?
#
# Requires a container runtime (docker / podman). Builds the sandbox image,
# mounts the target repo, and runs the gate in stages so a failure pinpoints
# exactly which step broke:
#   1. cargo check  -p selran-crypto   (the macOS/Linux keychain split — main risk)
#   2. cargo check  -p backend-rs      (the rest of the backend)
#   3. cargo build  -p backend-rs      (real compile + link on Linux)
#   4. boot + health  (Postgres + headless secret-service, launch, curl /api/health)
#
# Build cache (cargo registry + target) persists in named volumes, so re-runs
# after the first are incremental and fast.
#
# Usage:  ./sandbox/validate-linux.sh /path/to/target-repo
#
# Exit 0 = the backend builds and boots on Linux. Non-zero = the stage that failed.

set -uo pipefail

TARGET_REPO="${1:?usage: validate-linux.sh /path/to/target-repo}"
IMAGE="selran-devloop:latest"
RUNTIME="$(command -v docker || command -v podman || true)"

if [[ -z "$RUNTIME" ]]; then
  cat >&2 <<'MSG'
FAIL: no container runtime found (docker / podman).
The Phase 1 gate needs a Linux container to run. Install one of:
  - Docker Desktop / OrbStack
  - colima (brew install colima docker && colima start)
  - podman (brew install podman && podman machine init && podman machine start)
Then re-run this script.
MSG
  exit 2
fi

echo "[validate] runtime: $RUNTIME"
echo "[validate] building sandbox image..."
# Build context must be the repo ROOT (the Dockerfile does `COPY skills/`, and
# skills/ lives at the repo root, not in sandbox/). Point -f at the Dockerfile.
SANDBOX_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SANDBOX_DIR/.." && pwd)"
"$RUNTIME" build -t "$IMAGE" -f "$SANDBOX_DIR/Dockerfile" "$REPO_ROOT" || { echo "FAIL: image build" >&2; exit 1; }

# Run the gate. Source mounted read-only; build cache in named volumes so retries
# are incremental; CARGO_TARGET_DIR points at a volume (not the copied tree).
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

    echo "=== [1/4] cargo check -p selran-crypto (keychain split) ==="
    cargo check -p selran-crypto

    echo "=== [2/4] cargo check -p backend-rs ==="
    cargo check -p backend-rs

    echo "=== [3/4] cargo build -p backend-rs ==="
    cargo build -p backend-rs

    echo "=== [4/4] boot + health ==="
    # Postgres up. Add trust auth for loopback TCP so we connect without a
    # password (no embedded secret), then create the DB. v4 auto-migrates from
    # backend-rs/migrations/ at first boot, so no separate migrate step.
    service postgresql start || pg_ctlcluster "$(ls /etc/postgresql)" main start || true
    for n in $(seq 1 20); do pg_isready -h 127.0.0.1 -p 5432 && break; sleep 0.5; done
    PGHBA="$(ls /etc/postgresql/*/main/pg_hba.conf | head -1)"
    # pg_hba is FIRST-MATCH-WINS; Debian default scram line for 127.0.0.1 comes
    # before any appended line, so appending trust never takes effect. Rewrite
    # every auth method to trust (throwaway sandbox — no real data, no secrets).
    sed -i "s/scram-sha-256/trust/g; s/md5/trust/g; s/peer/trust/g" "$PGHBA"
    service postgresql restart || pg_ctlcluster "$(ls /etc/postgresql)" main restart || true
    for n in $(seq 1 20); do pg_isready -h 127.0.0.1 -p 5432 && break; sleep 0.5; done
    su postgres -c "createdb selran_mail_v4" 2>/dev/null || true

    # Env v4 needs to boot (from .env.example). Pin the bind port — v4 defaults
    # BACKEND_RS_BIND to 127.0.0.1:0 (a RANDOM port) that no fixed health check
    # could hit. SELRAN_ALLOW_REMOTE_AI=0 keeps it local-only.
    export DATABASE_URL="postgres://postgres@127.0.0.1:5432/selran_mail_v4"
    export BACKEND_RS_BIND="127.0.0.1:8765"
    export SELRAN_ALLOW_REMOTE_AI=0
    export RUST_LOG="info,backend_rs=debug"

    # Headless secret-service so selran-cryptos Linux keychain path has a daemon.
    # Throwaway, empty password — NEVER a real secret. Backend output goes to a
    # log so a boot failure shows WHY (not just curl connection-refused spam).
    dbus-run-session -- bash -euo pipefail -c "
      echo | gnome-keyring-daemon --unlock --components=secrets >/dev/null 2>&1 &
      sleep 1
      ( cargo run -p backend-rs > /tmp/backend.log 2>&1 & )
      for n in \$(seq 1 60); do
        if curl -fsS http://127.0.0.1:8765/api/health; then echo; echo PASS; exit 0; fi
        sleep 1
      done
      echo \"FAIL: health did not respond within 60s — backend log tail:\" >&2
      tail -40 /tmp/backend.log >&2
      exit 1
    "
  '
RC=$?
if [[ $RC -eq 0 ]]; then
  echo "PASS: backend builds and boots on Linux."
else
  echo "FAIL: validation gate failed at the stage shown above (rc=$RC)." >&2
fi
exit $RC
