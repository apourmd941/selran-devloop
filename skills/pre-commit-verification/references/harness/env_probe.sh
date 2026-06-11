#!/usr/bin/env bash
# Smoke test [7]: launch env — launchd-style stripped environment.
#
# Apps launched by the OS (Finder, launchd, Dock) inherit a MINIMAL environment,
# not your interactive shell's. Code that works in `cargo run` because PATH has
# brew/nvm/conda on it, or because some env var is set in your ~/.zshrc, fails
# when the OS launches the .app. This probe launches the binary under a stripped
# env (only an explicit PATH) to reproduce that condition.
#
# Exit 0 = boots cleanly under stripped env (PASS). Non-zero = FAIL.
#
# CUSTOMIZE: the binary, the minimal PATH, the health probe, and any env vars the
# app legitimately requires (those should be set by the bundle, not your shell).

set -uo pipefail

# CUSTOMIZE: path to the bundled binary (the thing launchd would run).
BINARY="${PROD_BUNDLE_BINARY:-dist/MyApp.app/Contents/MacOS/MyApp}"

# CUSTOMIZE: the minimal PATH a launchd-launched process actually gets on macOS.
MINIMAL_PATH="/usr/bin:/bin:/usr/sbin:/sbin"

# CUSTOMIZE: health check used to confirm the app actually came up.
HEALTH_URL="http://127.0.0.1:8765/api/health"
BOOT_WAIT_SECS=15

if [[ ! -x "$BINARY" ]]; then
  echo "FAIL: binary not found or not executable: $BINARY" >&2
  echo "(build the bundle first, or fix PROD_BUNDLE_BINARY)" >&2
  exit 1
fi

echo "[env-probe] launching under stripped env: PATH=$MINIMAL_PATH"
# env -i wipes the environment; we add back ONLY a minimal PATH (and HOME, which
# launchd does provide). Anything the app needs beyond this must be provided by
# the bundle/Info.plist, not by your shell.
env -i PATH="$MINIMAL_PATH" HOME="$HOME" "$BINARY" &
APP_PID=$!

cleanup() { kill "$APP_PID" 2>/dev/null || true; wait "$APP_PID" 2>/dev/null || true; }
trap cleanup EXIT

# Wait for health, mirroring the real launch.
deadline=$(( SECONDS + BOOT_WAIT_SECS ))
while (( SECONDS < deadline )); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "PASS: app booted and answered health under stripped env."
    exit 0
  fi
  # If the process already died, fail fast with its exit status.
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    wait "$APP_PID"; code=$?
    echo "FAIL: process exited (code $code) under stripped env before answering health." >&2
    echo "Likely a missing PATH dependency or env var your shell provides but launchd does not." >&2
    exit 1
  fi
  sleep 0.5
done

echo "FAIL: app did not answer health within ${BOOT_WAIT_SECS}s under stripped env." >&2
exit 1
