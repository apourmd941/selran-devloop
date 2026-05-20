#!/usr/bin/env bash
# Smoke test [2]: context-dependent — dev vs prod-bundled.
#
# The same scenario can pass in `dev` and fail when launched from the bundled
# `.app` (different working directory, different resource paths, different env,
# assets served from a bundle instead of a dev server). This runs the smoke
# suite under BOTH launch contexts and fails if either fails.
#
# This is a thin orchestrator: it sets the launch context, then delegates to the
# real smoke checks (the Rust health smoke test and/or the webview e2e). It does
# not duplicate their logic.
#
# CUSTOMIZE: how each context launches the binary, and which checks to run.

set -uo pipefail

FAILED=0

run_context() {
  local ctx="$1"; shift
  echo "================ context: $ctx ================"

  case "$ctx" in
    dev)
      # CUSTOMIZE: how the app is launched in dev (e.g. cargo build then the
      # debug binary, with the dev server origin).
      export SMOKE_BINARY="target/debug/backend"        # CUSTOMIZE
      export SMOKE_LAUNCH_CONTEXT="dev"
      ;;
    prod-bundled)
      # CUSTOMIZE: point at the built bundle so resource/asset paths match prod.
      # e.g. the binary inside the .app: MyApp.app/Contents/MacOS/MyApp
      export SMOKE_BINARY="${PROD_BUNDLE_BINARY:-dist/MyApp.app/Contents/MacOS/MyApp}" # CUSTOMIZE
      export SMOKE_LAUNCH_CONTEXT="prod-bundled"
      ;;
    *)
      echo "unknown context: $ctx" >&2; return 2 ;;
  esac

  # CUSTOMIZE: the checks to run under each context. Reuse the real harness tests
  # rather than reimplementing them.
  #   e.g. cargo test --test 'smoke_http_health' -- --nocapture
  #   and/or: npx playwright test e2e/ --grep @smoke
  if ! cargo test --test 'smoke_*' -- --nocapture; then
    echo "FAIL [$ctx]: smoke checks failed under $ctx" >&2
    return 1
  fi
  echo "PASS [$ctx]"
  return 0
}

for ctx in dev prod-bundled; do
  if ! run_context "$ctx"; then
    FAILED=1
  fi
done

if [[ "$FAILED" -ne 0 ]]; then
  echo "FAIL: smoke suite failed in at least one launch context (see above)." >&2
  exit 1
fi
echo "PASS: smoke suite passed under both dev and prod-bundled contexts."
exit 0
