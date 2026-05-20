#!/usr/bin/env bash
# Phase 1 validation gate — does the target's backend build and boot on Linux?
#
# Requires a container runtime (docker / podman). Builds the sandbox image,
# mounts the target repo, and runs the gate in stages so a failure pinpoints
# exactly which step broke:
#   1. cargo check  -p selran-crypto   (the macOS/Linux keychain split — main risk)
#   2. cargo check  -p backend-rs      (the rest of the backend)
#   3. cargo build  -p backend-rs      (real compile + link on Linux)
#   4. boot + health  (start Postgres + a headless secret-service, launch, curl /api/health)
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
"$RUNTIME" build -t "$IMAGE" "$(dirname "$0")" || { echo "FAIL: image build" >&2; exit 1; }

# Run the gate inside the container with the target repo mounted read-only and a
# fresh target/ dir so we never pollute the host build.
"$RUNTIME" run --rm \
  -v "$TARGET_REPO":/src:ro \
  -e CARGO_TARGET_DIR=/work/target \
  "$IMAGE" bash -euo pipefail -c '
    echo "=== copy source (keep host target/ clean) ==="
    cp -a /src/. /work/ 2>/dev/null || true
    cd /work

    echo "=== [1/4] cargo check -p selran-crypto (keychain split) ==="
    cargo check -p selran-crypto

    echo "=== [2/4] cargo check -p backend-rs ==="
    cargo check -p backend-rs

    echo "=== [3/4] cargo build -p backend-rs ==="
    cargo build -p backend-rs

    echo "=== [4/4] boot + health ==="
    # Postgres
    service postgresql start || pg_ctlcluster "$(ls /etc/postgresql)" main start || true
    # Headless secret-service so selran-crypto1s Linux keychain path has a daemon.
    # Throwaway, empty password — NEVER a real secret.
    dbus-run-session -- bash -euo pipefail -c "
      echo \"\" | gnome-keyring-daemon --unlock --components=secrets &
      sleep 1
      # CUSTOMIZE: launch command + health URL come from the repo1s autoloop.toml
      (cargo run -p backend-rs &)
      for i in \$(seq 1 30); do
        curl -fsS http://127.0.0.1:8765/api/health && { echo; echo PASS; exit 0; }
        sleep 1
      done
      echo \"FAIL: health did not respond within 30s\" >&2
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
