# Entry-Point Patterns

An "orphan file" warning in `warnings.json` fires when a source file has no `imported_by` entries — nothing in the codebase imports it. This usually signals dead code, but **entry points are legitimate orphans**: they're imported by the runtime, not by other source files. The build / runtime starts here.

Cartographer must recognize entry points and *not* flag them as orphans. This file is the recognition list.

When the orphan-file detector runs, check the file against these patterns first. If it matches, set `entry_point: true` on its `structure.json` entry and skip the orphan warning.

---

## Universal patterns (any language)

These names almost always indicate entry points regardless of language:

- `main.*` (main.rs, main.py, main.go, etc.)
- `index.*` (index.ts, index.js, index.html)
- `app.*` when at a project root or `src/` root
- `server.*`, `daemon.*`
- `cli.*` for CLI entry points
- `__main__.py` (Python module entry)

## JavaScript / TypeScript / Node

- `index.ts`, `index.js`, `index.tsx`, `index.jsx`
- `server.ts`, `server.js`
- `app.ts`, `app.js` at root
- Next.js: `pages/**/*.{ts,tsx}`, `app/**/page.{ts,tsx}`, `app/**/layout.{ts,tsx}`, `app/**/route.ts`, `middleware.ts`
- Remix: `app/routes/**`
- SvelteKit: `src/routes/**/+page.svelte`, `src/routes/**/+server.ts`, `src/app.html`
- Vite: `index.html` at project root
- Worker entry: `worker.ts`, `*.worker.ts`
- Service worker: `service-worker.ts`, `sw.ts`
- Electron: `main.ts` (main process), `preload.ts`, `renderer.ts`
- Test entries: files matching test patterns aren't orphans; they're invoked by the test runner

## Rust

- `src/main.rs` (binary entry)
- `src/lib.rs` (library root — technically imported by external consumers)
- `src/bin/*.rs` (additional binary targets)
- `examples/*.rs` (example binaries)
- `benches/*.rs` (benchmark entries)
- `tests/*.rs` (integration test entries)
- `build.rs` (build script)

## Python

- `__main__.py`
- `main.py`
- `app.py`, `server.py`, `wsgi.py`, `asgi.py`
- `manage.py` (Django)
- `setup.py`, `conftest.py`, `pyproject.toml` references
- Anything in `bin/` that's a script

## Go

- `main.go` in package `main`
- Files in `cmd/*/main.go` pattern

## Java / Kotlin

- Files containing a class with a `public static void main` (Java) or `fun main` (Kotlin)
- `Application.kt` / `Application.java` for Spring Boot

## Ruby

- `config.ru` (Rack)
- `app.rb`, `application.rb`
- `bin/*` executables

## Other config-driven entry points

These are tricky — the entry point is named arbitrarily but referenced from config. Check the relevant config files:

- `package.json`: `main`, `module`, `bin`, `exports` fields point to entry files
- `Cargo.toml`: `[[bin]]` and `[lib]` sections name entry files
- `pyproject.toml`: `[project.scripts]` entries
- `Dockerfile`: `CMD` and `ENTRYPOINT` directives often name a script
- `package.json` scripts (`"scripts": { "start": "node foo.js" }`) may identify entries
- Webpack / Vite / Rollup config: `entry` / `input` fields name entries

When Cartographer encounters a project with these config files, it should read them on full-build and extract the explicit entry points. Add those paths to a per-project allowlist in `state.json`:

```json
{
  "...": "...",
  "configured_entry_points": [
    "src/electron/main.ts",
    "src/electron/preload.ts",
    "src/renderer/index.tsx"
  ]
}
```

The orphan detector should consult this list as well as the universal patterns.

---

## Test files

Test files are a special case — they're orphans in the sense that no source file imports them, but they're not dead code: the test runner loads them. Cartographer already sets `test_file: true` on these (based on path patterns like `*.test.*`, `*.spec.*`, `tests/`, `test_*.py`). The orphan detector should treat `test_file: true` as suppressing the orphan warning.

---

## When in doubt

If a file looks like it might be an entry point but doesn't match any of these patterns, flag it as orphan **with low severity** and a note: "Looks like a possible entry point but doesn't match recognized patterns; verify."

That gives the user the information without crying wolf. Worse than missing a legitimate entry point is producing a flood of orphan warnings on a Next.js project (where 40 `page.tsx` files all genuinely have no `imported_by`).
