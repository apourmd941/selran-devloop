# Interview Protocol (Phase 3)

How to design, batch, and process the questions that turn a derived draft into a confirmed spec. The interview is the highest-value step of spec-bootstrap: the code already told us what the app does; only this step tells us what it *should* do.

---

## Question budget and batching

- **One round of 6–10 questions, at most three rounds.** Beyond ~25 total questions the user fatigues and starts rubber-stamping — which silently converts `[assumed]` to fake-`[confirmed]`, the worst possible outcome.
- Batch per round; never drip one question at a time.
- Group by theme (all deletion-semantics questions together), and put a one-line "why this matters" under each question so the user can answer with appropriate care.
- Multiple-choice where possible. "Should deletion (a) hard-delete, (b) soft-delete with 30-day purge, (c) soft-delete forever?" beats "what should deletion do?"

## Stakes ordering — what gets asked at all

Rank candidate questions by the cost of the spec being wrong, and spend the budget top-down:

1. **Irreversible loss**: deletion semantics, cascade behavior, backup coverage, "forget me" paths
2. **Security & privacy**: what's never logged, what never leaves the device, who can access what, credential storage
3. **Money / external side effects**: anything that sends, posts, charges, emails, or messages on the user's behalf
4. **Data integrity**: atomicity expectations, what happens on partial failure mid-pipeline
5. **Numeric bounds with unclear rationale**: thresholds, windows, caps found in code
6. **Missing capabilities**: no rate limit, no pagination, no offline path — decision or gap?
7. **Everything else** stays `[observed]`/`[assumed]` — that's fine; markers exist so the spec doesn't have to be complete to be honest.

## The three question archetypes

**1. Confirm the observed.**
> "The code requires confirmation before deleting a project (`routes/projects.rs:142`). Is 'no destructive action without confirmation' a rule for the whole app, or specific to projects?"

Generalizing matters: the user usually holds a *principle*, the code holds one *instance*. The principle is the spec statement; instances the code misses become findings.

**2. Surface the suspected accident.**
> "Failed categorization retries forever with no cap (`workers/categorize.rs:88`). Intended (transient-failure tolerance) or accident?"

Phrase neutrally — give the charitable reading alongside the suspicious one. The user saying "accident" creates an immediate finding AND a spec statement (the correct behavior, `[confirmed]`).

**3. Probe the absent.**
> "There's no export/backup path for user data. Decision (out of scope) or gap (should exist)?"

These produce the most valuable spec content: requirements the code doesn't meet yet. They're invisible to any code-only review — which is precisely why they survived every previous audit.

## Processing answers — the outcome table

| Answer | Spec effect | Side effect |
|---|---|---|
| "Yes, intended" | Statement → `[confirmed]` | — |
| "No, that's a bug" | Spec records the **correct** behavior `[confirmed]` | Entry in §Known-deviations → pre-seeded finding |
| "Intended for now, should change later" | Current behavior `[confirmed]` + a note | Optional roadmap note; NOT a finding |
| "Don't care / either is fine" | "Unspecified by choice `[confirmed]`" | Stops future re-asking |
| "I don't know yet" | Stays `[assumed]` | Entry in §Open-questions |
| User corrects the question's premise | Re-derive; the inventory was wrong | Check codemap drift — log it |

Every answer lands in exactly one row. An answer that just gets "noted" without updating the spec or seeding a finding was a wasted question.

## Anti-patterns

- **Leading the witness.** "The code does X, which is obviously wrong, right?" — you'll get agreement, not intent. Neutral framing with the charitable reading included.
- **Asking what the code already answers.** Don't ask "does the app use Postgres?" — ask only what code cannot reveal: intent, priority, tolerance.
- **Accepting vibes as confirmation.** "Sounds good" to a 9-question batch confirms nothing. If the stakes are tier-1/2, restate the single statement and get an explicit yes.
- **Burning budget on tier-7 trivia.** A label's wording can stay `[assumed]` forever at zero cost.
