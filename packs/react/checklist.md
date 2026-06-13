# react pack — checklist items (merged into the round's checklist, tagged [pack:react])

## Category 3 — Security
- [ ] No non-literal value reaches `dangerouslySetInnerHTML` without sanitization (rule covers the sink; verify the sanitizer is real, not a passthrough)
- [ ] No `href`/`src` built from user input without scheme validation (`javascript:` URLs)

## Category 4 — Error handling
- [ ] Data-fetching components have error boundaries or explicit error states (a thrown render kills the subtree)

## Category 6 — Resource bounds
- [ ] `useEffect` subscriptions/timers/listeners return cleanup functions (leak per re-mount otherwise)

## Category 7 — Spec/UX correctness
- [ ] List keys are stable identities, not array indexes, wherever lists reorder (silent state bleed between rows)
- [ ] No state initialized from props without an explicit sync strategy (stale-props bug class)
