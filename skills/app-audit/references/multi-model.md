# Multi-model review — cross-provider second opinions, consensus, local fallback

The mechanics behind app-audit Step 4.5.5 (cross-provider second opinion) and
audit-fix's cross-model challenge option. The idea: a finding that survives
scrutiny from a **different model family** is more trustworthy than one graded
only by the model that wrote it — different training, different blind spots.
But the layer is strictly **optional**: greenloop is complete without any
external CLI, degrades silently when none is present, and never blocks on one.

## §0 — Privacy gate (read this first)

Dispatching to an external provider **sends source code to another vendor's
API**. That is never an implied permission:

- **Ask once per repo, explicitly**, before the first external dispatch:
  > "A second opinion from <provider> means sending the relevant source files
  > to <vendor>'s API under your <CLI> account. OK for this repo? (Ollama runs
  > locally — nothing leaves the machine — if you'd rather use that.)"
- Record the answer in the chronicle (`.audit/CHRONICLE.md` lesson:
  "cross-provider consent: granted/declined <date>, providers: …") so the
  question isn't re-asked every round — but re-ask if the provider set changes.
- **Ollama is the privacy-preserving path**: local inference, nothing leaves
  the machine, no consent gate needed beyond the user invoking it.
- Never dispatch from a repo the user has marked sensitive, regardless of a
  generic earlier consent.

## §1 — Provider detection and invocation

Detect with `command -v`; use what's present, skip silently what isn't:

| Provider | Detect | Non-interactive invocation | Notes |
|---|---|---|---|
| OpenAI Codex CLI | `command -v codex` | `codex exec "<prompt>"` (add `--sandbox read-only` when supported) | reads repo from cwd |
| Gemini CLI | `command -v gemini` | `gemini -p "<prompt>"` | reads repo from cwd |
| Ollama (local) | `command -v ollama` and `ollama list` non-empty | `ollama run <model> "<prompt>"` | no repo access — paste the code into the prompt; prefer a code-tuned model the user already has |
| Others (opencode, etc.) | `command -v <cli>` | host's non-interactive/print mode | same contract: prompt in, text out |

Rules:
- **Bound every call** (`timeout 300 …`) and treat a non-zero exit / timeout as
  "provider unavailable this round" — log it, continue single-model. An audit
  must never hang on someone else's CLI.
- CLI flags drift; if an invocation errors on flags, try the bare form once,
  then mark unavailable. Don't debug a third-party CLI mid-audit.
- Version-log what ran: provider, CLI version (`codex --version` etc.), model
  if known — into the run metrics.

## §2 — Mode A: cross-model blind challenge (cheapest, use first)

Strengthens Phase 4.5: send each Critical/High finding to the external model
as a **blind challenge** — same contract as `gl-challenger` (claim + severity +
`file:line` + surrounding code, never the originating reasoning):

```
You are reviewing a claim about a codebase. Try to REFUTE it.
Claim: <finding title + description>
Severity claimed: <severity>
Code (<file>, lines N-M):
<code excerpt — enough context to judge>
Answer with exactly one verdict line: CONFIRMED | REFUTED | WEAKENED,
then 2-4 lines of reasoning grounded in the code shown.
```

Reconciliation (asymmetric by design):
- **CONFIRMED by external** → confidence +0.05 (on top of the internal
  challenge result); note `cross-model: confirmed (<provider>)`.
- **REFUTED by external** → does **NOT** remove the finding. It triggers one
  more internal examination of the external model's stated reason. If the
  reason holds on the code, the internal challenge removes it (and the cleared
  registry records "refuted with cross-model assist"); if it doesn't hold,
  keep the finding and note the disagreement.
- **WEAKENED / unparseable** → note it; no mechanical effect.

Only greenloop's own evidence-grounded challenge removes findings. External
verdicts are testimony, not verdicts of record.

## §3 — Mode B: independent second-opinion review (broader, costlier)

The external model reviews the **scope** independently (not the findings):
point it at the same change-set or hotspot files with the round's categories,
collect its findings, then merge like a detector's output:

- **Overlap with an existing finding** → consensus: confidence +0.10, cite
  `cross-model consensus (<provider>)`.
- **External-only finding** → treat exactly like an unconfirmed detector hit
  (Step 3.0 discipline): adjudicate by reading the cited code yourself; adopt
  it only if YOU can ground it (it then enters Phase 4.5 like any finding,
  marked `source: cross-model (<provider>), adjudicated`); discard silently if
  you can't — external models pad too.
- **Missed-by-external** → no effect. Absence of a second opinion is not
  evidence of absence.

Cost guidance: Mode B reads the whole scope through a second provider — for a
tight PR diff it's cheap; for whole-codebase rounds prefer Mode A plus Mode B
on the hotspot files only.

## §4 — Consensus gate (opt-in shipping bar)

Trigger: the user asks for "multi-model review" / "consensus review", or
`GREENLOOP_CONSENSUS=1`, or audit-fix runs at the **release threshold (0.99)**
with a provider available and consent granted.

The gate: the round/pass may not close green unless
1. every Critical/High fix survived a **cross-model blind challenge** (Mode A)
   in addition to the internal one, and
2. a Mode B second-opinion pass over the changed files surfaced **no
   adjudicated-and-grounded Critical** finding.

Failing the gate doesn't revert anything by itself — it reopens the specific
findings/fixes for the standard strengthen-or-rollback flow, and the close
report states plainly: `consensus gate: NOT MET (<which item, which provider>)`.
When no provider is available, the gate is **not silently skipped**: report
`consensus gate: requested but no provider available` so the user knows the
bar they asked for wasn't applied.

## §5 — Local models (Ollama) — weighting honestly

A local 7–30B model is a real second perspective but a weaker judge. Adjust:

- Confidence effects are **halved** (+0.025 challenge / +0.05 consensus).
- A local REFUTED triggers the same re-examination but its reasoning gets no
  benefit of the doubt — it must point at something concrete in the code.
- For the consensus gate, a local model **can** satisfy the second-challenger
  role but the close report must name the model so the user can judge the bar
  (`consensus via ollama/qwen2.5-coder:14b — local, reduced weight`).
- Prompt-size discipline: paste only the excerpt under judgment (local context
  windows are small); never feed it the whole diff and hope.

## §6 — What stays single-model

Phases 0–3 (baseline, cartography, scope, execution) and all enforcement
(hooks, read-only window) are greenloop-internal. The external layer exists
only where independence pays: challenge and second opinion. Don't outsource
finding *generation* wholesale — the codemap-grounded, checklist-driven pass
IS the product; the second model is a skeptical reader, not a co-author.
