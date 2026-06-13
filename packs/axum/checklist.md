# axum pack — checklist items (merged into the round's checklist, tagged [pack:axum])

## Category 3 — Security
- [ ] No `CorsLayer::permissive()`/`Any` origin on routers serving data (rule covers the literal; check layer ordering too — layers wrap only routes registered BEFORE them)
- [ ] Loopback binding is not treated as authentication — any browser tab can reach 127.0.0.1 (field-proven finding class)
- [ ] Extractors that can panic (`.unwrap()` on `Extension`/`State`) replaced with fallible forms in handlers

## Category 5 — Concurrency
- [ ] Shared state behind `Arc<Mutex/RwLock>` audited for `.lock().unwrap()` poisoning behavior under panic
- [ ] No `std::sync::Mutex` held across `.await` (deadlock class; use tokio's)

## Category 8 — Operational readiness
- [ ] Graceful shutdown wired (`with_graceful_shutdown`) so in-flight requests drain on deploy
