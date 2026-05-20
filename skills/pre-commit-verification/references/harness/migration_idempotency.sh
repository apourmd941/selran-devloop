#!/usr/bin/env bash
# Smoke test [3]: stateful DB — migration idempotency.
#
# Fresh DB -> run migrations -> run migrations AGAIN -> assert the second run is
# a clean no-op. This catches migrations that aren't idempotent: re-running them
# (which happens on every boot in many setups) errors or double-applies. Unit
# tests almost never exercise "run migrations twice".
#
# Exit 0 = idempotent (PASS). Non-zero = FAIL with detail on stderr.
#
# CUSTOMIZE the four variables below for your stack, then wire into the harness
# entry point (make smoke / cargo test wrapper / npm script).

set -euo pipefail

# CUSTOMIZE: how to create a throwaway database for the test.
#   Postgres example: a temp database; SQLite example: a temp file.
TMP_DB_URL="${SMOKE_DB_URL:-postgres://localhost/smoke_migration_test}"

# CUSTOMIZE: command that creates the empty database (no schema yet).
create_db() {
  # e.g. createdb smoke_migration_test
  # or for sqlite: rm -f "$SQLITE_PATH"
  echo "CUSTOMIZE: create_db not implemented" >&2
  return 1
}

# CUSTOMIZE: command that drops/cleans the throwaway database.
drop_db() {
  # e.g. dropdb --if-exists smoke_migration_test
  :
}

# CUSTOMIZE: the command that applies all pending migrations against TMP_DB_URL.
run_migrations() {
  # e.g. sqlx migrate run --database-url "$TMP_DB_URL"
  # or:  diesel migration run --database-url "$TMP_DB_URL"
  # or:  cargo run --bin migrate -- "$TMP_DB_URL"
  echo "CUSTOMIZE: run_migrations not implemented" >&2
  return 1
}

cleanup() { drop_db || true; }
trap cleanup EXIT

echo "[migration-idempotency] creating fresh DB: $TMP_DB_URL"
create_db

echo "[migration-idempotency] first migration run (expected: applies schema)"
if ! first_out="$(run_migrations 2>&1)"; then
  echo "FAIL: first migration run errored" >&2
  echo "$first_out" >&2
  exit 1
fi

echo "[migration-idempotency] second migration run (expected: clean no-op)"
if ! second_out="$(run_migrations 2>&1)"; then
  echo "FAIL: migrations are NOT idempotent — second run errored." >&2
  echo "----- second run output -----" >&2
  echo "$second_out" >&2
  exit 1
fi

# CUSTOMIZE (optional): assert the second run reported zero applied migrations.
# Many tools print "no migrations to apply" or similar. Tightening this catches
# migrations that silently re-apply (e.g. CREATE without IF NOT EXISTS that
# happens to not error but does redundant work).
# if ! grep -qiE "no .*migrations|nothing to|0 applied|up to date" <<<"$second_out"; then
#   echo "FAIL: second run did work — migrations not a clean no-op." >&2
#   echo "$second_out" >&2
#   exit 1
# fi

echo "PASS: migrations are idempotent (second run was a clean no-op)."
exit 0
