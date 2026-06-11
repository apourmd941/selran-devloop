# Severity Grading: Examples

When uncertain about a finding's severity, consult this. The goal is consistent grading across audit rounds so the user can prioritize reliably.

**Rule of thumb:** when a finding could be either of two severities, **grade up** and explain why. Optimistic grading is how audits miss the things that matter.

---

## Critical

Will definitely cause data loss, security breach, or unrecoverable user-facing failure under normal use.

| Example | Why critical |
|---|---|
| SQL query built by string concatenation of user input | Injection vulnerability; trivial to exploit |
| OAuth refresh token logged to a file Time Machine backs up | Token leakage to backup systems and telemetry |
| Bulk delete operation without confirmation gate | Single click destroys user data; spec says "never auto-delete" |
| Forget primitive (GDPR) only deletes from primary table, not embeddings | Legal liability; user-promised invariant violated |
| Migration that drops a column the app still writes to | Production data loss on next deploy |
| Auto-send code path in a product whose spec says "never auto-sends" | Highest user-trust violation |
| Race condition that can corrupt a message body during concurrent write | Data corruption with no recovery path |
| Plaintext password stored in DB | Single breach exposes everything |

**Test:** would I want this deployed to production for an hour? If no, it's Critical.

---

## High

Will likely cause significant problems under realistic conditions.

| Example | Why high |
|---|---|
| Worker race condition: two workers can both flip status from pending → processing | Causes duplicate work, possible duplicate side effects, not corruption |
| Missing index causing 30s query on a path users hit daily | Performance becomes user-visible quickly |
| Error path that silently swallows exceptions in a worker | Real failures hidden, debugging becomes guesswork |
| Schema constraint missing where the spec requires it (e.g., FK not enforced) | Allows the bad state to exist; bugs become possible that shouldn't be |
| Reactive UI subscriber doesn't reconnect on disconnect | Users see stale data after network blip; trust erodes |
| Backoff missing on retry loop; failure storms hammer downstream | Cascading failures under load |
| Confidence threshold from spec not enforced in surface code | Spec violation visible to user as "noise"; trust impact |
| Unbounded queue that fills under realistic burst load | Memory exhaustion or worker stall |

**Test:** if this hit production, would the user notice within a week? If yes, it's High.

---

## Medium

Will cause problems in edge cases, or causes ongoing pain that isn't blocking.

| Example | Why medium |
|---|---|
| List query with no pagination on a table that grows slowly | Will be a problem eventually; not today |
| Awkward but informative error message exposed to user | Annoying, not dangerous |
| Table that will grow unbounded over years, no compaction job | Slow-burn issue |
| Two-name typo in a function ("Catagorize" vs "Categorize") | Hard to grep for; reduces maintainability |
| Console.log in production code path | Noise in logs; not a real bug |
| Worker pool size hardcoded; should be configurable | Inflexible; not broken |
| `derivations` table indexed by `id` but queries always filter by `target_id` | Inefficient queries; not catastrophic at small scale |
| Schema migration not idempotent | Rerunning would fail; cleanup is annoying |

**Test:** if I never fixed this, would the product still ship and work? If yes, it's at most Medium.

---

## Low

Minor improvements; cleanups; not bugs.

| Example | Why low |
|---|---|
| Code duplication across three files | Maintainability hit; works correctly |
| Dead code path no longer reachable | Cruft; not a bug |
| Suboptimal but correct pattern (e.g., `.map().filter()` instead of single pass) | Cosmetic |
| Missing inline documentation on a non-public function | Maintainability |
| Inconsistent variable naming (`userId` vs `user_id` in same module) | Style |
| Dev dependency not pinned | Slight reproducibility hit |

---

## Info

Observations, not findings. The user might or might not care.

| Example | Why info |
|---|---|
| "This module is 4x larger than the next-largest; consider splitting before it grows further." | Heads-up |
| "The `messages` table will be the largest by an order of magnitude — confirm indexes are right." | Awareness |
| "Two patterns for handling X exist in different parts of the codebase; consolidating would help future readers." | Suggestion |
| "Test coverage for module Y is lower than the rest of the codebase." | Observation |

---

## Common grading mistakes

**Grading by intent rather than impact.** A logging bug is graded by what gets exposed, not by what the developer meant to log. "It was supposed to be a debug log" doesn't change the severity if a token actually leaks.

**Grading by likelihood rather than impact when likelihood is unknown.** A race condition that you "haven't observed in practice" is graded by what happens when it triggers, not by guessed frequency. If the impact is corruption, it's High or Critical regardless of how rare.

**Grading down because "the fix is small."** Severity is about impact, not effort. A 1-line fix for a Critical issue is still Critical.

**Grading up to inflate the report.** Don't promote Lows to Mediums to make the audit look more substantive. A short, sharp report with correct severities beats a padded one.

**Grading inconsistently across rounds.** If round 1 graded "missing index" as High and round 2 grades a similar finding as Medium without justification, the user can't trust the severities. Stay consistent or explain why context changes the grade.

---

## Severity for spec-compliance findings (Category 7)

Spec-compliance findings often deserve **higher severity than the same finding would get if the spec didn't mention it.** A user-facing promise is a higher-stakes invariant than an unspecified implementation detail.

Examples:

- Code violates a spec "never": typically Critical or High, because the user has been promised this won't happen.
- Code violates a spec numeric bound (e.g., uses 24 months instead of 12): typically High, since the product behaves differently than documented.
- Code uses a different internal pattern than the spec suggests, but with equivalent behavior: Medium or Low — the spec is descriptive here, not promissory.

When in doubt for spec-compliance, ask: "Did the user read the spec and rely on this?" If yes, grade up.
