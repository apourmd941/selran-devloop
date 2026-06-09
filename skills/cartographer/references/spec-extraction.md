# Spec_refs Extraction (v0.3.0)

How cartographer populates `spec_refs` on source files AND on individual functions. Two paths: explicit annotations (always trusted) and inferred mappings (gap-filling, with confidence thresholds). v0.3.0 extends the v0.2.1 file-level extraction with function-level propagation (Stage 2 of the build).

Read this when implementing or refining cartographer's spec-extraction logic, or when a user asks why a file or function got a particular spec_ref.

---

## The two paths, side by side

| Source | When applied | Confidence | Recorded as |
|---|---|---|---|
| **Explicit annotation** in source file (`@spec: v3 §8.1`) | Always, no gating | 1.0 (implicit) | `{"ref": "v3 §8.1", "source": "explicit"}` |
| **Inferred** by cartographer reading file + spec | Only for files matching high-value tag profiles, only when confidence ≥ 0.7 | 0–1 score | `{"ref": "v3 §8.1", "source": "inferred", "confidence": 0.82}` |

Explicit always wins. If a file has `@spec: v3 §8.1` and inference would also suggest `v3 §8.2`, both are recorded (one explicit, one inferred) — they're not in conflict.

If explicit and inferred would produce the same ref, deduplicate to keep the explicit entry only.

**Execution-path difference:** the table's "inferred by cartographer reading file + spec" row describes the **direct path** (Claude doing the build inline). The **script path** (`_build.py`) cannot read and reason about the spec — its only inference source is the project's `tag_spec_map` in `.codemap/spec-config.yml`, and with no map configured it records explicit refs only. The template ships no hardcoded tag→section numbers; those are project-specific by nature.

---

## Function-level propagation (v0.3.0 — Stage 2 of the build)

In addition to file-level spec_refs, v0.3.0 populates spec_refs on individual functions in `functions.json`. The procedure for each extracted function:

1. **Inherit the file's spec_refs.** Initialize the function's `spec_refs` to a shallow copy of the file's `spec_refs` array.

2. **Scan nearby comments.** Look at the 4 lines of source code immediately above the function signature. For each `§N.M` pattern found (e.g., `// See §3.2 for the contact identity model.`), add it to the function's `spec_refs` as `{"ref": "§N.M", "source": "explicit", "confidence": 1.0}` — but only if it isn't already inherited from the file.

3. **No model-based inference at the function level.** Per-function inference would be prohibitively expensive; the file-level inference plus the comment scan covers the practical cases.

This means a function in `auth/refresh.ts` (file tagged `auth`, file has inferred spec_ref `§8.1`) will inherit `§8.1`. If a comment above the function says `// implements: v3 §8.1.3`, then `§8.1.3` is also recorded with `confidence: 1.0` (explicit).

Function-level spec_refs let consumers (especially `app-audit` category 7) answer queries like "find every function implementing §8.1" without having to read every file. The cost is small — propagation is free, the 4-line comment scan is nearly free.

For everything else (explicit annotation patterns, inference procedure, confidence calibration, cost discipline), the file-level rules below apply equally to v0.3.0.

---

## Explicit annotation extraction

Scan every source file for these comment patterns. Language-agnostic — works across TS, Rust, Python, etc.

**Single-line forms:**

```
// @spec: v3 §8.1
// @spec v3 §8.1
# @spec: v3 §8.1
-- @spec: v3 §8.1     (SQL)
```

**Multi-line forms:**

```
/**
 * @spec v3 §8.1
 * Other doc text...
 */

"""
@spec: v3 §8.1
"""
```

**Alternate keywords (less common but accepted):**

- `@implements:` — treated identical to `@spec:`
- `// implements: v3 §X.Y` — same
- `// see-spec: v3 §X.Y` — same

**Normalization:** all extracted refs are normalized to `"v<version> §<section>"` form. Section identifier preserved as-written, but version stamp normalized:

- `v3 §8.1`, `V3 §8.1`, `v3.0 §8.1`, `v3 section 8.1` → all normalize to `"v3 §8.1"`

If the spec version in the annotation doesn't match the canonical spec's `spec_version`, record both and log a warning in the run summary:

> "Found explicit spec_refs to `v2 §8.1` in src/auth/refresh.ts, but canonical spec is v3. Possible stale annotation."

---

## Inferred extraction — when it runs

Inferred extraction is **gated** to keep token cost bounded. Only run inference on source files where **at least one** of these is true:

- File has any of these tags: `auth`, `security-sensitive`, `db`, `data-model`, `schema`, `worker`, `concurrency`, `api`, `crypto`, `external-api`, `pause-resume`, `migration-runner`
- File is at a recognized entry point (per `entry-point-patterns.md`) AND has substantive `purpose`
- File's `purpose` (already extracted at structure-build time) explicitly mentions a concept matching a section title in the canonical spec

For files outside this gate, `spec_refs` remains empty unless an explicit annotation populates it. This is the right tradeoff — inferring spec mappings for utility files, formatters, and other non-architectural code wastes tokens for low value.

---

## Inference procedure

For each gated file:

1. **Read the canonical spec's section list.** This was extracted at documentation-class build time and lives internally (not in structure.json). The list is `[{ref, title, summary_chars: 200}]` for each top-level section.

2. **Read the file's `purpose` (already extracted) and a small portion of its code** — typically the first ~80 lines or the top 3 function bodies. Don't read the whole file; the goal is signal, not deep analysis.

3. **Ask the model: "Does this file implement any of these spec sections?"** Provide the section list and the file excerpt. Get back a JSON response with candidate matches and confidence scores.

4. **Filter and record.** Drop any candidate below confidence 0.7. Record the rest as `{"ref": <section>, "source": "inferred", "confidence": <float>}`.

5. **Cap at 3 inferred refs per file.** A file that "implements 7 sections" probably has wrong inference — keep the top 3 by confidence and drop the rest. If 4+ legitimate matches actually exist, the developer should add explicit annotations.

---

## Confidence calibration

The inference model returns a confidence score per candidate ref. Calibrate generously toward false negatives (better no inference than wrong inference):

| Confidence | Meaning | Recorded? |
|---|---|---|
| 0.9–1.0 | The file purpose and code directly describe the section's claim | Yes |
| 0.7–0.9 | Strong match — file probably implements this section, but other interpretations exist | Yes |
| 0.5–0.7 | Plausible match — would be helpful but not certain. **Not recorded.** | No |
| 0.3–0.5 | Weak match — section is related but file doesn't directly implement it | No |
| Below 0.3 | No real match | No |

If at any point a calibration mistake is found ("this confidence 0.85 inference is clearly wrong"), surface it in warnings.json under `codemap_drift` and don't re-infer that pair on next refresh.

---

## Cost discipline

Inferred extraction is the most expensive part of cartographer's build. Token cost roughly scales as:

`(gated_files) × (~1.5K tokens spec section list + ~2K tokens file excerpt + ~500 tokens response)`

For a typical project: 30–100 gated files × 4K tokens = 120K–400K tokens on first build. On incremental refresh, only files that changed get re-inferred — usually a handful per refresh, negligible cost.

**Optimization: batch by file similarity.** If 5 files all have tag `worker` and similar purposes, infer them in one model call with all 5 file excerpts and ask for matches per file. This cuts the per-file overhead by ~3×.

**Optimization: cache by file content hash.** If a file's content hash matches what's in `state.json.per_file_state`, its inferred refs from the last build are still valid. Don't re-infer.

---

## Surfacing inferred refs to the user

After a full build (or upgrade refresh), report the inferred refs summary:

```
Spec_refs populated:
- 12 files via explicit @spec annotations
- 35 files via inference (confidence ≥ 0.7)
- 178 gated files yielded no high-confidence inference (recorded as no spec_refs)
- 298 ungated files (not in inference scope)

Highest-confidence inferences:
  - src/auth/refresh.ts → v3 §8.1 (0.94)
  - src/workers/categorize.rs → v3 §1.3, v3 §3.7 (0.88, 0.85)
  - src/db/contacts.rs → v3 §3.2 (0.82)
  ...
```

Suggest the user spot-check a few inferred refs by reading the file + spec section pair to verify correctness. If a few are wrong, that's information about how to recalibrate (e.g., the spec section titles are too vague, or the file purposes are misleading).

---

## When inference is the wrong tool

If audit Category 7 (spec compliance) keeps generating findings of the form "this file says it implements §X.Y but it doesn't actually," that's a sign inference is too aggressive. Two responses:

1. **Tighten the inference gate.** Restrict to fewer tag profiles.
2. **Raise the confidence threshold.** From 0.7 to 0.8.

Don't disable inference entirely — explicit annotations alone leave too many gaps in practice. Just calibrate it conservatively.
