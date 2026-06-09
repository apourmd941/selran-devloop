# Smoke/Integration Harness Templates

Manifest of the harness templates, what each one catches, and how to scaffold them into a project. Read this before scaffolding (SKILL.md "Scaffolding the harness").

These templates exercise the **launched** system — the failure classes unit tests structurally cannot catch, because unit tests run in a sanitized context (mocked DB, mocked providers, no real binary, no real webview). The pattern mirrors cartographer's `_build.py`: copy into the project once, customize the marked points, then the project owns them and pre-commit-verification runs them on every pass.

## Template manifest

| # | Failure class | Template | Stack | What it proves |
|---|---|---|---|---|
| 1+4 | runtime + build-graph | `smoke_http_health.rs` | Rust backend | The built binary boots, the health route answers 200 under a real cross-origin request, CORS header is present, and the process logs on startup |
| 2 | context-dependent | `dev_prod_matrix.sh` | any | The smoke suite passes under **both** dev and prod-bundled launch contexts — "works in dev, 500s in the bundle" is this class |
| 3 | stateful DB | `migration_idempotency.sh` | any with migrations | Fresh DB → migrate → migrate **again** → second run is a clean no-op. Catches unguarded CREATEs that break every boot after the first |
| 5 | browser quirks | `webview_e2e.spec.ts` | Tauri/Electron | Headless automation drives the actual `.app` webview, not a mocked DOM |
| 7 | launch env | `env_probe.sh` | any | The app boots under a stripped environment (`env -i PATH=...`, launchd-style) — catches "works in my shell, dies when the OS launches it" |
| 8 | external APIs | `provider_mock_test.rs` | Rust backend | Provider contracts pinned with fixtures (wiremock/httpmock) so upstream drift is caught locally |
| 9 | UX | `onboarding_clickthrough.spec.ts` | webview/web | Click-through automation of onboarding-style flows |

Category **6** (missing layers — e.g., required CORS middleware for a cross-origin webview) is deliberately **not** a runtime template. It's a static presence check owned by app-audit's security category; the [1+4] template catches the *behavioral* half at runtime. Presence ≠ correct behavior — both halves are needed.

## Scaffolding guidance

1. Only copy the categories that apply to the stack. A pure CLI tool doesn't need `webview_e2e.spec.ts`; an app with no DB doesn't need `migration_idempotency.sh`.
2. Default locations: `tests/smoke/` for Rust tests (so `cargo test --test 'smoke_*'` finds them), `e2e/` for Playwright-style specs, `scripts/` or `tests/smoke/` for the shell harnesses.
3. Every template marks its project-specific bits with `CUSTOMIZE` comments — binary path, health URL, webview origin, DB URL, migration command. Fill in what's known from the repo; leave a TODO for what isn't.
4. Wire the harness into the repo's verification entry point — a `make smoke` target, an npm script, or the cargo test-name pattern — so future verification passes discover it without re-reading this skill.
5. **Never re-scaffold over an existing harness.** The project's copies are authoritative; these templates are starting points, not a source of truth to overwrite.

## Safety notes

- The shell templates follow the safe server-launch pattern from SKILL.md (PID capture, bounded readiness polls, `timeout` wrapping, kill-by-PID — never bare `wait`, never `%`-job control). Keep that pattern when customizing; it's what prevents the harness from hanging the whole verification.
- Harness tests are heavier than unit tests (real processes, real DBs, real webviews). Keep each one focused on its failure class; resist expanding them into long manual-QA scripts.
- A flaky harness test gets made deterministic, not deleted (SKILL.md guardrails).
