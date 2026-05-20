# Selran DevLoop — sandbox image (Phase 1)
#
# A disposable Linux environment with the toolchain to build, boot, and smoke-test
# a Selran app (backend + web-frontend). The native macOS Tauri shell is NOT built
# here — that's the deferred Tier 3 (macOS VM).
#
# Build:  docker build -t selran-devloop:latest sandbox/
# Use:    the autoloop driver clones a target repo's branch into /work and runs
#         the loop (cartographer → app-audit → audit-fix) inside this container.

FROM rust:1-bookworm

# ---- system deps ----------------------------------------------------------
# - postgresql-client + a local postgres for the migration/idempotency smoke
# - libssl/pkg-config for crates that touch TLS (most use rustls, but be safe)
# - the secret-service stack (dbus + gnome-keyring) so selran-crypto's Linux
#   keychain path (keyring 3.x + sync-secret-service) has a daemon to talk to.
#   Without this, the crate COMPILES but the app fails at boot reaching the
#   keychain over D-Bus. See docs/DESIGN.md §3 and sandbox/validate-linux.sh.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates pkg-config libssl-dev \
        postgresql postgresql-client \
        dbus gnome-keyring libsecret-1-0 \
        libdbus-1-dev \
        nodejs npm \
    && rm -rf /var/lib/apt/lists/*
# NOTE: libdbus-1-dev is REQUIRED — selran-crypto's Linux keychain backend
# (keyring 3.x + sync-secret-service) pulls in libdbus-sys, whose build script
# needs the D-Bus C headers + pkg-config. Confirmed by Phase 1 cross-check:
# the Rust compiles fine; only libdbus-sys needs these dev headers. See
# sandbox/PHASE1-FINDINGS.md.

# ---- pgvector -------------------------------------------------------------
# your-rust-app's migration 1 uses the `vector` type, so the extension must be
# present or the backend fails at first-boot migration. (v4 logs "vector
# features will be runtime-disabled" when pgvector is absent, but the migration
# still hard-requires the type — a v4 inconsistency flagged for a later audit;
# the sandbox just provides the extension.) Built from source against PG15.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential postgresql-server-dev-15 \
    && git clone --depth 1 --branch v0.8.0 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && make -C /tmp/pgvector OPTFLAGS="" && make -C /tmp/pgvector install \
    && rm -rf /tmp/pgvector \
    && apt-get purge -y build-essential postgresql-server-dev-15 \
    && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# ---- node toolchain (frontend build + Playwright-WebKit) ------------------
# Playwright's WebKit engine runs headless on Linux — this is how the
# web-layer frontend smoke/e2e (harness categories 5 + 9) run without a Mac.
RUN npm install -g playwright@latest \
    && npx --yes playwright install --with-deps webkit

# ---- the four methodology skills -----------------------------------------
# Copied to the location Claude Code reads at runtime so the loop driver can
# load cartographer / pre-commit-verification / app-audit / audit-fix.
COPY skills/ /root/.claude/skills/

# ---- workspace ------------------------------------------------------------
# The driver mounts/clones the target repo's branch here at runtime.
WORKDIR /work

# A throwaway secret-service session can be started at container start so the
# keychain path works headless. The driver/entrypoint runs:
#   dbus-run-session -- sh -c 'echo "" | gnome-keyring-daemon --unlock; ...'
# (Kept out of the image so secrets are never baked in.)

CMD ["/bin/bash"]
