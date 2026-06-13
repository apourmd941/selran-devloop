# fastapi pack — checklist items (merged into the round's checklist, tagged [pack:fastapi])

## Category 3 — Security
- [ ] CORS: explicit `allow_origins` list; never wildcard with credentials (rule covers the literal case; verify no env-driven wildcard either)
- [ ] Auth enforced via router-level `dependencies=[Depends(...)]`, not per-route memory (one forgotten route = open endpoint)
- [ ] No `pickle`/`eval` on request-derived data (rule covers direct cases)

## Category 4 — Error handling
- [ ] Exception handlers don't leak internals (stack traces, SQL, paths) in responses
- [ ] Pydantic validation errors return 422 with safe messages, not raw repr of input

## Category 8 — Operational readiness
- [ ] App run with `reload=False` / no debug server in production entrypoints
- [ ] Startup/shutdown events (or lifespan) close DB pools and clients — verify, leaks survive tests
