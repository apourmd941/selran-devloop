# Self-learning — chronicle, cleared registry, learned rules, shared brain

The mechanics behind app-audit Step 1.5 (load learned context), Step 4.5.1/4.5.4
(cleared registry), Step 5.5 (learn from the round), and audit-fix Step 5.2
(fix lessons). The principle: an audit that rediscovers the same facts every
round is paying for the same knowledge twice. Lessons persist; findings don't
repeat; recurring patterns become deterministic checks.

Three stores, three scopes:

| Store | Scope | Contains |
|---|---|---|
| `.audit/CHRONICLE.md` | this repo | lessons, cleared registry, fix lessons |
| `.audit/learned-rules/` | this repo | detector rules codified from recurrences |
| `~/.greenloop/brain.md` | all repos (opt-in) | privacy-scrubbed, stack-keyed pattern lessons |

Commit policy: the chronicle and learned rules follow the repo's `.audit/`
policy; for team repos, committing them is recommended — they're institutional
memory, and the whole point is that the next auditor (human or model) inherits
them. The brain never leaves the user's home directory.

## §1 — Chronicle format (`.audit/CHRONICLE.md`)

```markdown
# Audit chronicle — <repo>
<!-- loaded into context every round: keep under ~200 lines; prune superseded
     entries instead of appending forever -->

## Lessons
- [2026-06-12] Tests require `FOO=1` (discovered round 3 — harness env probe).
- [2026-06-12] Migration 0042 intentionally non-idempotent — user confirmed;
  do not re-flag (finding 3.2, round 2).
- [2026-05-30] lib/net.ts retry wrapper swallows errors BY DESIGN (spec §4.2).

## Cleared registry
- claim: "TOCTOU between stat and open" @ src/cache.rs:88
  cleared: 2026-06-12, HEAD a1b2c3d, blind challenge
  reason: file is created O_EXCL two lines up — race window doesn't exist
- claim: "SQL injection via user filter" @ api/search.py:41
  cleared: 2026-05-30, HEAD 9f8e7d6, self-challenge
  reason: parameterized via ORM; string concat is on a literal

## Fix lessons
- pattern "missing tx on multi-write": wrapping at the route layer broke
  nested-tx tests — wrap at the repository layer instead (round 2, finding 4.1).
- clean-room delta round 3: `config_local.py` was untracked and load-bearing —
  now committed as config_local.example.py.
```

Rules:
- **Terse, dated, factual.** One or two lines per entry. The chronicle is
  context, not a journal — AUDIT_LOG.md already narrates the rounds.
- **Prune on write.** When appending in Step 5.5, delete entries that are
  superseded (the file was removed, the lesson got codified into a rule, the
  spec now documents the oddity). Target < 200 lines.
- **User-confirmed intent goes here**, not just in a finding's dismissal —
  dismissals live per-round in AUDIT_LOG; the chronicle is what guarantees
  round N+5 still knows.

## §2 — Cleared-registry matching (Step 4.5.1 pre-check)

A new finding matches a cleared entry when **all three** hold:

1. **Same claim** — the asserted defect is the same class ("TOCTOU", "injection
   via X", "unbounded growth of Y"), not merely the same file.
2. **Same location** — same file and same function/block; line drift is fine
   (use the function from the codemap's `loc_range`, not the raw line number).
3. **Code unchanged since clearing** — `git log --since` / blame on the cited
   range shows no commits after the entry's `cleared:` SHA-date.

Match → drop the finding silently; count it in Step 4.5.4 as a
`cleared-registry hit`. No match on condition 3 (code changed) → the clearing
has expired; challenge fresh, and if it's refuted again, UPDATE the entry's
SHA/date rather than adding a duplicate.

The registry must never become an immunity blanket: it suppresses
*re-litigation of unchanged code*, nothing else. When in doubt about condition
1 or 2, challenge normally — a duplicate challenge is cheap; a silently
suppressed real defect is not.

## §3 — Learned detector rules (`.audit/learned-rules/`)

### When to codify

A pattern qualifies when it recurred **3+ times** (same category + same root
cause, across this round and AUDIT_LOG history) AND is mechanically detectable
— a syntactic or structural signature a tool can match. "Handlers call
.unwrap() on request data" qualifies; "error messages are unhelpful" doesn't
(that stays a `[learned]` checklist item only).

### Formats

Prefer a semgrep rule (one YAML file per rule):

```yaml
# .audit/learned-rules/unchecked-unwrap-in-handlers.yml
# learned 2026-06-12 from findings 2.1, 3.4, 5.2 (rounds 2-3)
rules:
  - id: unchecked-unwrap-in-handlers
    languages: [rust]
    severity: WARNING
    message: ".unwrap() on request data in a handler — recurring pattern in this repo (see chronicle)"
    paths:
      include: ["src/api/**", "src/handlers/**"]
    pattern: $REQ.$FIELD().unwrap()
```

When semgrep can't express it (or isn't installed), a grep pattern file:

```
# .audit/learned-rules/raw-sql-concat.grep
# learned 2026-05-30 from findings 1.2, 1.5, 4.3 — run with: grep -rnE -f this-file src/
"SELECT .*" *\+ *
execute\(f"
```

Step 3.0 runs everything in the directory:
`semgrep --config .audit/learned-rules/ --json` plus each `*.grep` via
`grep -rnE -f`. Cite hits as `learned-rule <id> (codified <date> from findings <ids>)`.

### Lifecycle

- **Born** at Step 5.5 with user approval (headless runs never create rules).
- **Header comment is mandatory** — date + source findings; a rule nobody can
  trace is a rule nobody trusts deleting.
- **Demoted** when it fires only false positives for two consecutive rounds:
  Step 3.0 flags it, Step 5.5 offers retirement (move to
  `.audit/learned-rules/retired/` — keep the file; it documents that the
  pattern was considered).
- **Retired automatically** when the checklist item it backs is removed, or the
  pattern's root cause is eliminated structurally (e.g., the team adopted a
  lint rule that subsumes it — note which one in the retired file).

## §4 — Recurrence detection (Step 5.5)

Signature for "the same finding pattern": **category + root-cause class +
code-shape**, NOT file/line. Build it per finding from the audit's own fields:
the category, the one-phrase root cause ("missing transaction", "unvalidated
external input", "resource not bounded"), and the syntactic shape if one exists
(API called, idiom used). Count across:

- this round's findings (3 instances in one round qualifies), and
- AUDIT_LOG history (2 this round + 1 in round N-2 qualifies),
- regardless of status — FIXED instances still count toward recurrence; the
  pattern keeps being *written*, which is exactly why it needs a detector.

Don't over-trigger: 3 findings that share a category but not a root cause
("three security findings") are not a recurrence. The test: could one rule or
one checklist sentence have caught all instances? If not, it's not a pattern.

## §5 — Shared brain (`~/.greenloop/brain.md`) and the privacy scrub

Format — stack-keyed sections, pattern lessons only:

```markdown
# Greenloop brain — cross-project lessons (privacy-scrubbed)

## rust/axum
- CORS layer order: .layer() applies only to routes registered BEFORE it —
  register routes first, layers last. (learned: 2 projects)

## python/fastapi
- TestClient hides loopback-binding bugs — also probe the real bound socket
  once per harness run.
```

Step 1.5 reads only the sections matching the repo's detected stack; entries
are **priors to check**, never findings ("the brain says check X" → check X,
grade what you actually observe).

### The privacy scrub (mandatory before any write)

A lesson crosses repos only as a **pattern description**. Before writing,
strip and verify:

1. **No identifiers**: repo names, product names, org names, author names.
2. **No paths**: `src/api/handlers.rs` → "in handlers". No URLs, no hostnames,
   no ports that aren't framework defaults.
3. **No code quotes**: rewrite as the idiom's description ("string-formatted
   SQL in an f-string"), never pasted lines.
4. **No business logic**: what the code *does commercially* stays behind. The
   lesson must read as true of any project on that stack.
5. **Counter only**: provenance is `(learned: N projects)` — never which ones.

Show the scrubbed entry to the user before writing; write only on yes. Never
offer distillation from a repo the user has marked sensitive. The brain is
plain markdown the user can open, edit, and delete — say so when creating it.
