# Build Stages (v0.3.0)

Cartographer v0.3.0 extracts function-level information in four stages. This file documents each stage in detail: what it populates, how it works, the cost, and when to invoke it.

Read this when implementing or debugging cartographer's function extraction, when the user asks "why is functions.json missing X?", or when deciding whether to enable stage 4 for a particular project.

---

## Stage overview

| Stage | Populates | Default | Cost | When useful |
|---|---|---|---|---|
| 1 | function `tags` | On | Free | Always — never disable |
| 2 | function `spec_refs` + file `spec_refs` | On | ~10% extra | Always — never disable |
| 3 | `qualified_name` + `last_modified_commit` | On | ~5% extra | Always — never disable |
| 4 | function `calls` + `called_by` | Opt-in | +30-60s build, +30-50% audit tokens | When blast-radius matters |

Stages 1, 2, 3 are always on because they're cheap and high-value. Stage 4 is opt-in because it's expensive enough to justify a choice.

---

## Stage 1 — Tag propagation

**What it does:** copies the file's tags down to each function defined in that file.

**Why it's valuable:** consumers (especially `app-audit`) can query "all functions tagged `auth`" or "all functions in `worker` files" without re-reading the file. This is the cheapest possible enrichment.

**Mechanism:** in `extract_rust_functions()` (or the equivalent for other languages), the file's tag list is passed in as a parameter. Each function's `tags` array is initialized to a shallow copy of the file's tags.

```python
for fn in extracted_functions:
    fn["tags"] = list(file_tags)  # shallow copy so per-function additions don't pollute the file's list
```

**Per-function additions.** In the simple form, functions inherit file tags exactly. In a future enhancement, function-specific tags could be added (e.g., a single function in a non-test file is marked `test`, or a single function in a routine file is marked `security-sensitive`). For v0.3.0, only file tags propagate.

**Cost:** zero. The file's tags are already computed; copying them is free.

**Failure modes:** none material. If file tags are wrong, function tags will inherit that wrongness — but that's a tag inference problem, not a stage 1 problem.

---

## Stage 2 — Spec_refs propagation

**What it does:**
1. Computes file-level `spec_refs` by combining explicit `@spec:` annotations with tag-based inference
2. Copies file-level refs to each function's `spec_refs`
3. Scans the 4 comment lines above each function signature for additional `§N.M` references
4. Adds those scan-detected refs to the function's `spec_refs` as `source: "explicit"`, confidence 1.0

**Why it's valuable:** audit's category 7 (spec compliance) becomes a JSON query. "Find every function claiming to implement §8.1" → grep `functions.json`. Without this, audit has to re-derive spec refs every time.

**Mechanism (file-level):** see `references/spec-extraction.md` for the full inference procedure. In brief:

- **Explicit refs** — scan the file for `@spec: vN §X.Y`, `// implements: vN §X.Y`, etc. Record as `{"ref": "vN §X.Y", "source": "explicit", "confidence": 1.0}`.
- **Inferred refs** — for files matching high-value tag profiles (`auth`, `security-sensitive`, `db`, `worker`, etc.), apply tag-to-spec-section mappings with confidence scores. Record those with confidence ≥ 0.7.
- **Confidence calibration** — false positives are worse than false negatives. Tune toward fewer wrong refs.

**Mechanism (function-level):** the function extractor takes `file_spec_refs` as a parameter. Each function's `spec_refs` is initialized to a copy of the file's refs. Then for each function, the extractor looks at the 4 lines immediately above the function signature for `§N.M` patterns. Each match becomes an additional ref with `source: "explicit"`, confidence 1.0.

```python
# Stage 2 — function-level scan
nearby_refs = list(file_spec_refs)  # shallow copy
seen = {r["ref"].lstrip("§") for r in nearby_refs}
for k in range(max(0, sig_line - 4), sig_line):
    for m in SPEC_REF_RE.finditer(lines[k]):
        ref = m.group(1)
        if ref not in seen:
            nearby_refs.append({
                "ref": f"§{ref}",
                "source": "explicit",
                "confidence": 1.0,
            })
            seen.add(ref)
fn["spec_refs"] = nearby_refs
```

**Cost:** about 10% extra build time. The file-level inference is the expensive part (one model call per gated file, see `spec-extraction.md` for cost discipline). Function-level propagation and the 4-line scan are nearly free.

**Failure modes:**
- Wrong tag → wrong inferred ref. Mitigated by confidence threshold.
- Stale `@spec:` annotation (file claims §8.1 but the code no longer implements it). Cartographer can't detect this; audit category 7 catches it later.

---

## Stage 3 — Qualified names + git blame

**What it does:**
1. Computes each function's `qualified_name` as `<crate>::<module>::<function>` (Rust) or `<package>.<module>.<function>` (Python) or `<file path without suffix>` (TS/JS)
2. Runs `git log -1 --format=%H -- <file>` per file to get the last-modified commit hash
3. Stamps every function in that file with `last_modified_commit`

**Why it's valuable:**
- `qualified_name` makes cross-file function references unambiguous. `categorize` is ambiguous; `backend-rs::services::mail::categorize::categorize` is not.
- `last_modified_commit` lets audit-fix correlate fixes to commits and detect "this function changed recently and is now flagged" patterns.

**Mechanism (qualified_name):** the `compute_qualified_prefix()` helper builds the prefix from the file path. The function extractor appends `::<function_name>` for each function it extracts.

For Rust:
```
backend-rs/src/services/mail/imap_sync.rs::fetch_messages
↓
backend-rs::services::mail::imap_sync::fetch_messages
```

For Python:
```
scripts/build/foo.py::compute
↓
scripts.build.foo.compute
```

For TS/JS, the path is kept as-is (no canonical module system) — the prefix becomes the file path with the suffix stripped.

**Mechanism (git blame):** `subprocess.run(["git", "log", "-1", "--format=%H", "--", file])` per file. The hash applies to every function in the file (the function-level blame would be more precise but vastly more expensive). The result is stored once per file and copied to every function.

**Caching:** since incremental refresh only re-runs stages 1-3 on files whose content hash changed, the git-blame call only fires for changed files. On a typical refresh, 5-10 files change, so this is 5-10 subprocess calls — negligible.

**Cost:** about 5% extra. Dominated by subprocess overhead on `git log`.

**Failure modes:**
- Non-git environment → `last_modified_commit` is empty string for all functions. Not fatal.
- Rust files outside the `src/` convention → qualified_name falls back to path-based form. Slightly less canonical but still unique.
- Functions inside `impl` blocks → in v0.3.0, the impl context isn't captured in qualified_name. A future improvement would prefix with the impl target (`MyStruct::method`). Current behavior produces just `<file>::method`, which is still unique within the file.

---

## Stage 4 — Call graph extraction (opt-in)

**What it does:** for every function in the codebase, scan its body for identifiers that match other functions' names. Record edges in each function's `calls` array (outgoing) and `called_by` array (incoming).

**Why it's valuable:**
- **Blast-radius grading.** `audit-fix` orders fixes by how many call sites a change might affect. Without call graph, blast radius is grade by file imports — coarse-grained. With call graph, blast radius is graded by actual function callers — precise.
- **Caller queries.** "What calls `ensure_token_fresh`?" becomes a direct lookup instead of a grep.
- **Hot-path identification.** Functions with many callers are hot paths. Cartographer can surface these as priorities for tests, monitoring, etc.

**Why it's opt-in:** the cost is real on both sides:
- **Build cost:** 30-60 seconds for a typical project (1,000-5,000 functions). Goes up with codebase size.
- **Consumption cost:** `functions.json` grows by ~30-50% when call graph is populated. Audit-fix reading the codemap costs more tokens.

For projects with simple architectures, the precision gain isn't worth the cost. For complex projects (many cross-module calls, security-sensitive code, refactoring in progress), it is.

**Mechanism:** regex-based identifier matching, with stdlib filtering.

```python
# 1. Build lookup of name → list of qualified_names defining that name
name_lookup = {}
for fn in all_functions:
    name_lookup.setdefault(fn.name, []).append(fn.qualified_name)

# 2. For each function body, scan for identifier(...) patterns
SKIP_NAMES = {"new", "unwrap", "Vec", "Option", ...}  # stdlib/keywords
for caller in all_functions:
    body = read_function_body(caller)
    for match in re.finditer(r"([a-z_][a-zA-Z0-9_]*)\s*\(", body):
        called_name = match.group(1)
        if called_name in SKIP_NAMES:
            continue
        for callee_qname in name_lookup.get(called_name, []):
            if callee_qname == caller.qualified_name:
                continue  # skip self-recursion
            record_edge(caller.qualified_name, callee_qname)
```

**Limitations of regex extraction:**
- **False positives.** A variable named `request` and a function named `request` are indistinguishable. Mitigated by the SKIP_NAMES filter and by the precondition that the matched identifier must be followed by `(`.
- **Missed dynamic dispatch.** Trait objects, function pointers, dynamic imports — invisible.
- **Method dispatch ambiguity.** `obj.method(x)` matches `method` to all functions named `method` in the codebase. Without type information, cartographer can't disambiguate.

Precision in practice: ~70-85% on typical Rust codebases. Good enough for blast-radius grading. Not sufficient for precise refactoring.

**Future upgrade:** swap regex for tree-sitter (via `tree-sitter-rust` Python bindings) or `syn` (via a subprocess to a small Rust helper binary). Either would push precision to ~95% at the cost of 2-3x slower build and a build-time dependency. Worth doing if user feedback says the regex version produces too many false positives.

**Caching:** results are written to `.codemap/_call_graph_cache.json`:

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-19T01:00:00Z",
  "files_covered": ["path/to/file1.rs", "path/to/file2.rs", ...],
  "edges": {
    "backend-rs::services::mail::categorize::categorize": {
      "calls": [{"target": "backend-rs::db::insert"}, ...],
      "called_by": [{"caller": "backend-rs::workers::ingest::run_once"}, ...]
    },
    ...
  }
}
```

On subsequent runs, cartographer checks the cache's `files_covered` against the current file set. If ≥90% of files are unchanged, the cache is fresh — apply edges directly to functions.json without re-extraction.

If less than 90% overlap, the cache is stale. Cartographer either prompts the user, runs unconditionally (if `--with-call-graph`), or skips (if `--non-interactive` without `--with-call-graph`).

To force-rebuild: `--rebuild-call-graph`.

---

## The opt-in flow for stage 4

There are five invocation patterns:

**1. Explicit invocation: `--with-call-graph`**

Run stage 4 unconditionally. Used when the user knows they want it.

```bash
python3 .codemap/_build.py --with-call-graph
```

**2. Skip: `--no-call-graph`**

Skip stage 4 even if the cache exists. Used when the user wants a deliberately-fast build.

```bash
python3 .codemap/_build.py --no-call-graph
```

**3. Force rebuild: `--rebuild-call-graph`**

Run stage 4 and replace the cache. Used when the user knows the cache is stale beyond the 90% threshold.

```bash
python3 .codemap/_build.py --rebuild-call-graph
```

**4. Non-interactive (default for hooks): `--non-interactive`**

Never prompt. Skip stage 4 unless `--with-call-graph` is also passed. Used by the SessionStart hook so it doesn't block on input.

```bash
python3 .codemap/_build.py --non-interactive
```

**5. Interactive (default): no flag**

If the cache is fresh (≥90% overlap), reuse it silently.
If the cache is stale or missing, prompt the user:

```
cartographer: Stage 4 (call graph extraction) is optional.
  - It produces richer audit-fix blast-radius grading.
  - It costs an additional ~30-60 seconds at build time.
  - It increases app-audit token cost by roughly 30-50% when consumed.

Run stage 4 now? [y/N]:
```

The user answers. Cartographer respects the choice.

---

## When Claude (not the script) decides about stage 4

When Claude is running cartographer on the user's behalf — not via the standalone script — Claude makes the stage 4 decision based on context:

**Default to OFF when:**
- The user just said "refresh the codemap" or "use cartographer" without specifying scope
- The SessionStart hook is firing
- The build is happening alongside other work and speed matters

**Turn ON when:**
- The user explicitly asks for call graph, calls, called-by, or blast radius information
- The user is about to run `audit-fix` on a substantial set of findings (more than 10) — call graph improves the ordering
- The audit being prepared touches blast-radius-sensitive categories (Cat 3 security, Cat 5 concurrency, Cat 1 schema)
- The user says "deep refresh", "full rebuild", or "with everything"

**Always mention** that stage 4 is available when relevant. A user who doesn't know it exists can't opt in. A short note in the run summary suffices:

> "Stage 4 (call graph) is available — would add ~30s and ~30% more tokens but would let audit-fix grade blast radius precisely. Want me to run it?"

---

## What to look at if stage 4 results look wrong

**Symptom: too many edges to common stdlib types**

The `SKIP_NAMES` list isn't comprehensive enough. Add the offending names (e.g., `into_iter`, `as_ref`, `borrow`) to the skip list.

**Symptom: missing edges for known calls**

Either the called function's name doesn't appear in `name_lookup` (it wasn't extracted — check `functions.json` for it), or the regex isn't matching the call site (uncommon syntax like turbofish `::<>` patterns).

**Symptom: every function has the same self-call**

Probably matching the function's own name inside its own body. Cartographer's stage 4 explicitly skips edges where caller and callee are the same qualified name, but if you see this, the skip logic isn't firing — file a bug.

**Symptom: stage 4 runs forever**

Codebase is too large for the regex approach. Either narrow the scope (run cartographer on a subdirectory) or skip stage 4 and rely on file-level blast radius from `imported_by`.

---

## Future improvements (not in v0.3.0)

- **Tree-sitter-based call extraction** for 95%+ precision
- **Per-function git blame** instead of per-file (more precise `last_modified_commit`)
- **Cross-language call tracking** (Rust → TypeScript via Tauri IPC, Python → Rust via PyO3, etc.)
- **Stage 5 — pattern detection** (functions with similar bodies, suggesting refactor opportunities)
- **Stage 6 — coverage integration** (cross-reference with `cargo llvm-cov` or `tarpaulin` output to mark function as `tested: true/false`)

These are wishlist items; not in v0.3.0 and not on a fixed roadmap.
