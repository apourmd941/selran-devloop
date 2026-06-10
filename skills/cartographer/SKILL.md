---
name: cartographer
version: 0.5.0
description: Build and maintain a persistent codemap (.codemap/*.json — structure, dependencies, functions, warnings) of any codebase. Function-level extraction runs in four stages — tags, spec_refs, qualified names + git blame default-on; call graph opt-in. Use whenever the user asks to build, refresh, or rebuild the codemap; to map the code; to find duplicate, stale, or unused files; or as part of an audit (app-audit Phase 0.5). Incremental refresh after the first full build. Works on any language.
---

# Cartographer

Build and maintain persistent, structured maps of a codebase. Cartographer reads the source tree, extracts what each file is and how the pieces relate, and writes the result as JSON in `.codemap/` so future sessions (and skills like `app-audit`) can consult the maps instead of re-scanning.

## Why this exists

Two real problems Cartographer solves:

1. **Token cost of repeated scanning.** Without persistent maps, every time Claude needs "every file that touches OAuth" or "every function that updates DB state," it has to re-grep the codebase. With the maps, the answer is a direct JSON lookup.
2. **Running stale code.** A real failure mode: you fix a bug, run the app, nothing changes — and only later realize the running code was loading `auth.old.ts` instead of `auth.ts`. Cartographer's `warnings.json` proactively surfaces duplicate filenames, suspicious naming patterns, backup directories, orphan files, and near-duplicate content — the conditions that produce that failure.

The maps are persistent and incrementally refreshed. Initial build is expensive (one pass over the codebase). Subsequent refreshes only re-analyze changed files.

## When to use this skill

Trigger Cartographer when the user asks to:

- Build, refresh, update, or rebuild the codemap
- Find duplicate, stale, orphan, or unused files
- Check what depends on a specific file or function
- Get an overview of "what is this codebase"
- Diagnose "running stale code" or mysterious version issues

Trigger automatically when:

- `app-audit` runs Phase 0.5 (codemap freshness check)
- A session starts in a project with `.codemap/` and `state.json` is materially behind HEAD

## What Cartographer produces

Five files in `.codemap/` at the repo root:

```
.codemap/
├── structure.json         — where every file lives, what it is, what it's for
├── dependencies.json      — what each file imports, what imports it
├── functions.json         — function-level details (signatures, calls, tags, spec_refs, qualified names, blame)
├── warnings.json          — duplicates, suspicious names, backup dirs, orphans, near-duplicates, canonical designations
└── state.json             — internal: last-built commit, per-file content hashes, build metadata
```

A sixth file appears only when the call-graph stage has run:

```
.codemap/_call_graph_cache.json   — opt-in cache of function-to-function call edges (stage 4)
```

The cache is reused across runs as long as ≥90% of files are unchanged.

Full schemas: `references/codemap-schemas.md`.

## Two execution paths — pick one per project

Cartographer can run in either of two ways, and a project should pick one and stick with it:

**Script path (recommended for any non-trivial project).** A project-level Python script at `.codemap/_build.py` does the extraction. Faster, deterministic, easy to invoke from a SessionStart hook. The skill ships a template at `references/_build.py` — copy it into the project's `.codemap/` on first install or when the skill template changes.

```bash
cp ~/.claude/skills/cartographer/references/_build.py /path/to/project/.codemap/_build.py
```

The script writes `state.json.cartographer_version` matching the `CARTOGRAPHER_VERSION` constant in the template header (check the template, don't hardcode an expectation — this doc and the script have drifted before) and `state.json.build_metadata.build_method = "py-script-richer"`. If the project's `state.json` shows an older version than the current template, the template wasn't re-copied after a skill upgrade — the most common gotcha. The script detects this itself: a version mismatch triggers an automatic full rebuild on next run.

**Script capabilities — the honesty contract.** The script records exactly what it can do in `state.json.capabilities`: which warning detectors ran (`detectors_run`), which languages got function/import extraction, and that import resolution and the stage-4 call graph are best-effort static analysis. **Skills that consume the codemap (app-audit, audit-fix) must read `capabilities` before trusting a field** — if a detector or language isn't listed, that data wasn't produced and the consumer falls back to inline analysis (Read/Grep) for that piece. An empty array in `warnings.json` means "detector ran, found nothing" only when the detector appears in `detectors_run`.

**Direct path (small projects, no Python available, ad-hoc one-offs).** Claude does the extraction inline using its own tools (Read, Grep, etc.). Slower and less deterministic than the script, but useful when there's no `_build.py` and the project is small enough that token cost is fine.

For the rest of this document, "Cartographer runs" means either path. Where the two paths diverge, it's called out explicitly.

## Function-level extraction stages

Cartographer extracts function-level information in four stages. Stages 1–3 are default-on (run on every build and refresh). Stage 4 is opt-in (the user is prompted, or it's invoked via flag/skill hand-off).

| Stage | What it populates | Default | Cost |
|---|---|---|---|
| 1 — Tag propagation | Each function's `tags` (inherits the file's tags) | On | ~0 |
| 2 — Spec_refs propagation | Each function's `spec_refs` (inherits file refs + scans 4 comment lines above the signature) | On | ~10% extra build time |
| 3 — Qualified names + git blame | Each function's `qualified_name` (module path) and `last_modified_commit` | On | ~5% extra build time |
| 4 — Call graph | Each function's `calls` and `called_by` arrays | **Opt-in** | +30–60s build, +30–50% audit token cost |

Full details on each stage and the cache-reuse policy: `references/build-stages.md`.

**Why stage 4 is opt-in:** call-graph extraction adds real cost on both sides — slower build and a larger `functions.json` (which means anything consuming the codemap pays more tokens). For simple architectures, the cost isn't worth it. For complex projects (security-sensitive code, many cross-module calls, refactors in progress), it is. The prompt lets the user decide per project.

When Cartographer runs directly (not via the script), Claude:

- Defaults to **not** running stage 4
- Mentions stage 4 is available if the user wants richer call-graph data
- Runs stage 4 when the user explicitly asks ("with call graph", "include calls", "I want to know what calls X")
- Runs stage 4 automatically when `audit-fix` invokes Cartographer in its Phase 0 (audit-fix's tier classification requires `called_by`)

When Cartographer runs via the script, the flags are:

```bash
python3 .codemap/_build.py                       # interactive — prompts for stage 4 if cache stale
python3 .codemap/_build.py --non-interactive     # never prompts; stage 4 off unless --with-call-graph
python3 .codemap/_build.py --with-call-graph     # run stage 4 unconditionally
python3 .codemap/_build.py --no-call-graph       # skip stage 4 even if the cache is fresh
python3 .codemap/_build.py --rebuild-call-graph  # force-rebuild the stage 4 cache
python3 .codemap/_build.py --full                # ignore prior state; full rebuild
```

The script refreshes incrementally by default: each file's content hash is compared against `state.json.per_file_state`, and unchanged files reuse their prior analysis (no re-extraction, no per-file `git log`). Only changed, new, or deleted files pay the cost. `--full` forces a from-scratch rebuild.

The SessionStart hook should use `--non-interactive`, otherwise the script will block on the prompt.

### Stage 4 cache

When stage 4 runs, it writes `.codemap/_call_graph_cache.json`, including a per-file content-hash snapshot. On subsequent runs, if ≥90% of current files have **unchanged content** (hash comparison, not just file presence), the cache is reused silently. Below 90%, the cache is treated as stale (re-extracted or skipped per the flags above).

### What a rich function entry looks like (stages 1–3 active)

```json
{
  "name": "refresh_token",
  "qualified_name": "backend::services::oauth::refresh_token",
  "signature": "pub async fn refresh_token(account_id: &str) -> Result<TokenPair, AuthError>",
  "loc_range": [42, 78],
  "calls": [],
  "called_by": [],
  "tags": ["rust", "auth", "security-sensitive"],
  "spec_refs": [
    {"ref": "§8.1", "source": "explicit", "confidence": 1.0},
    {"ref": "§8.2", "source": "inferred", "confidence": 0.80}
  ],
  "exported": true,
  "last_modified_commit": "abc123def456"
}
```

With stage 4 also active, `calls` and `called_by` are populated.

## Core workflow

Two main operations: **full build** (first run, or rebuild) and **incremental refresh** (every subsequent run).

### Full build

Use when:
- `.codemap/` doesn't exist
- User explicitly asks for a rebuild
- `state.json` is corrupted or its schema version is incompatible
- The codemap is so stale (e.g., 50+ commits behind) that incremental refresh would cost more than rebuilding

**Steps:**

1. **Set expectations.**
   > "Building the codemap from scratch. One-time cost — future refreshes will only re-read changed files."

2. **Walk the source tree.** Respect `.gitignore`. Skip:
   - `node_modules/`, `.venv/`, `target/`, `dist/`, `.next/`, `build/`, generated output directories
   - `.git/`, `.DS_Store`, lock files
   - `.claude/` — excluded so the walk never descends into Desktop-dispatched code-task worktrees (`.claude/worktrees/<name>/`), which are full copies of the repo. Without this, every worktree file is double-counted as a duplicate of the real source.
   - Anything matched by `.gitignore`

3. **For each source file, extract:**
   - Language (typescript, rust, python, …)
   - Lines of code
   - Imports and exports
   - Functions and their signatures
   - Function bodies (only as needed for stage 4)
   - Comments tagged with spec refs (e.g., `// @spec: §8.1`)
   - Content hash (SHA-256)
   - Last modification time from `git log`

4. **Infer purpose and tags per file.** Read the file (or just the top portion) and decide:
   - One-sentence `purpose`
   - Tags from the controlled vocabulary (`references/tag-vocabulary.md`): `auth`, `db`, `worker`, `ui`, `api`, `test`, `config`, `security-sensitive`, `concurrency`, `external-api`, etc.
   - Spec refs if the file matches a known section of the design spec (`references/spec-extraction.md`)

5. **Build cross-references.** Once all files are analyzed:
   - For each `imports_from` entry, populate the corresponding `imported_by` on the target file
   - For each function `calls` entry, populate `called_by` on the target function (stage 4 only)

6. **Run warning detectors.** See "Warning detectors" below.

7. **Write all five JSON files.** Schemas in `references/codemap-schemas.md`. Pretty-print for diff readability.

8. **Commit recommendation.** Don't auto-commit, but tell the user:
   > "Codemap written to .codemap/. Recommend committing — these files are institutional memory, useful across machines and team members. Merge conflicts (any JSON file gets them) are resolved by re-running cartographer."

### Incremental refresh

Use when `.codemap/` already exists at the current schema version and the user asks to refresh, or `app-audit` Phase 0.5 invoked us.

**Steps:**

1. **Read `state.json`** for `last_full_build_commit` and per-file content hashes.

2. **Identify changed files.** Two signals:
   - `git diff --name-status <last_full_build_commit>..HEAD` for committed changes
   - Compare current SHA-256 of each file on disk against the hash in `state.json` (catches uncommitted changes and works even if git is in an odd state)

3. **For each changed file:**
   - If deleted: remove its entries from all four codemap files
   - If renamed: update the path everywhere (treat as delete + add, then patch up)
   - If new or modified: re-run the per-file extraction from full-build step 3

4. **Patch cross-references for affected files.** If file A's imports changed, update `imported_by` on the old and new targets. If function signatures changed, update `called_by` on functions this one used to / now calls (stage 4 only).

5. **Re-run warning detectors.** These run over the codemap JSONs (no file I/O) and are cheap.

6. **Update `state.json`:** new `last_refresh_commit`, refreshed content hashes, bumped `last_refresh_at`.

7. **Report what changed:**
   > "Refreshed N files (X added, Y modified, Z deleted). Warnings.json updated. Cross-references patched on M affected files."

## Warning detectors

Run over the codemap to produce `warnings.json`. These directly address the "running stale code" failure mode.

### Detector 1 — Duplicate basenames

Any filename that appears in more than one location, e.g. `auth.ts` in both `src/auth/` and `src/legacy/`. Severity: **high** if both are imported anywhere, **medium** if only one is.

Why: ambiguous imports may resolve to the wrong file, and the running app may load a different version than the developer expects.

**Exception:** basenames that are duplicated *by convention* are never flagged — `mod.rs`, `lib.rs`, `__init__.py`, `index.ts`, Next.js `page.tsx`/`layout.tsx`/`route.ts`, `README.md`, `Cargo.toml`, `package.json`, and the like. The list lives in `CONVENTIONAL_BASENAMES` in `_build.py`; extend it per project rather than tolerating noise.

### Detector 2 — Suspicious names

Match filenames against patterns that signal stale or backup files:
- `*.old.*`, `*.OLD.*`
- `*.backup.*`, `*.bak.*`, `*.bkp.*`
- `*_old.*`, `*_backup.*`, `*_archive.*`
- `*_v[0-9]+.*` (versioned files: `auth_v2.ts`, `handler_v3.rs`)
- `*-copy*`, `*_copy*`, `*Copy.*`
- `*DELETE*`, `*REMOVE*`, `*TODO_REMOVE*`
- `Untitled.*`, `New File.*`

Severity: **medium** for any match. The file may be legitimate, but the name is a smell that needs human review.

**Exception:** files inside `migrations/` directories are excluded from the `*_v[0-9]+.*` pattern. Migration files like `0003_org_map_v2.sql` are sequenced, not stale.

### Detector 3 — Backup directories

Find directories matching:
- `*_backup*`, `*_archive*`, `*_old*`
- `OLD_*`, `BACKUP_*`, `ARCHIVE_*`
- `src_*` when `src/` also exists at the same level (e.g., `src_2026_04/`)
- Dated suffixes: `*_YYYY_MM_DD`, `*_YYYYMMDD`

Severity: **high** if inside the build path; **medium** elsewhere.

### Detector 4 — Orphan files

A source file with empty `imported_by` is either an entry point (`server.ts`, `main.rs`, `index.ts`) or dead code. Cross-reference against known entry points (`references/entry-point-patterns.md`).

Severity: **medium** for non-entry-point orphans.

### Detector 5 — Near-duplicate content

For pairs of files in the same directory (or with similar paths), compute content similarity. If ≥85%, flag as near-duplicate. Severity: **high**.

Implementation: shingling on lines or tokens, Jaccard similarity over hash sets. Only compare pairs that already share directory and have similar lengths — global pairwise comparison is too expensive.

This is the detector that most directly catches unfinished refactors.

### Detector 6 — Stale build output (older than source)

In generated output directories (`dist/`, `build/`, `.next/`, `out/`):
- Output whose newest file is **older** than the latest source change — the launched app may be serving stale code

Severity: **medium**. The fix is a rebuild. (`target/` is excluded — cargo manages its own staleness. Orphaned outputs with no corresponding source are a direct-path check; the script only does the mtime comparison.)

### Detector 7 — Canonical version designation

For every cluster of duplicate-basename or near-duplicate files from detectors 1 and 5, designate **one** as canonical. The non-canonical members are flagged as "stale candidates."

Designation algorithm (priority order):

1. **Import-graph reachability.** If only one duplicate is reachable from a known entry point, that one is canonical. The others are dead. If imports are *split* between candidates, designation is **ambiguous** (see below).
2. **Most recent meaningful commit.** Among files that are all reachable (or all orphaned), pick the one whose latest non-cosmetic commit is newest. (The script approximates this with the latest commit touching the file, no cosmetic filtering; the direct path can be smarter.)
3. **Higher LOC and lower suspicious-name score.** `auth.ts` beats `auth.old.ts` even at similar commit ages.
4. **First alphabetically by path.** Last-resort tiebreak, recorded as `alphabetical_tiebreak` with a note that it was arbitrary — treat like `ambiguous` for review purposes.

Recorded in `warnings.json` under `canonical_designations`:

```json
"canonical_designations": [
  {
    "cluster": ["src/auth/refresh.ts", "src/auth/refresh_v2.ts"],
    "canonical": "src/auth/refresh.ts",
    "stale_candidates": ["src/auth/refresh_v2.ts"],
    "designation_reason": "import_graph_reachability",
    "concern": "src/auth/refresh.ts is imported by src/workers/sync.ts; refresh_v2.ts has no imported_by entries.",
    "severity": "high",
    "suggested_action": "Remove src/auth/refresh_v2.ts or archive outside source tree."
  }
]
```

**When designation is ambiguous** (algorithm produces ties or imports are split between candidates), set `designation_reason: "ambiguous"`, severity `high`, and surface it prominently — these are the cases most likely to produce "running stale code" failures.

`app-audit` consumes this: any finding located in a `stale_candidates` file is downgraded to **Info** unless the user explicitly directs attention there.

## Documentation files

Cartographer processes documentation alongside source. Every doc gets classified into one of three classes and entered in `structure.json` with `kind: "documentation"`. High-information specs are also used to populate `spec_refs` on source files.

### Triage — three classes

**`spec` class** — high-information docs that describe what the code should do. Match any of:
- Filename matches `*DESIGN*.md`, `*SPEC*.md`, `*PLAN*.md`, `*ROADMAP*.md`, `ARCHITECTURE.md`, `*-v[0-9]*-design.md`
- Or contains 3+ section markers that look like spec references: `§\d`, `## \d+\.\d+`, `### \d+\.\d+\.\d+`
- Or listed under `canonical_spec` or `supporting_docs` in `.codemap/spec-config.yml`

Spec-class docs get full processing: file entry in `structure.json`, used for inferred spec_refs extraction on source files.

**`operational` class** — files describing project conventions: `AGENTS.md`, `CONTRIBUTING.md`, `STYLE.md`, `UI_DESIGN_PRINCIPLES.md`, anything in `spec-config.yml`'s `operational_docs`. File entry + tags, but not used for spec_refs inference.

**`informational` class** — `README.md`, `CHANGELOG.md`, miscellaneous notes. File entry in `structure.json`, minimal metadata.

**Excluded entirely** — anything under `node_modules/`, `vendor/`, `target/`, `.git/`, archive directories already flagged as such, plus anything `.gitignore`'d.

### spec-config.yml — naming the canonical spec

Cartographer can guess which doc is the canonical spec by filename patterns and section-marker density, but ambiguity is common. The user disambiguates with an optional `.codemap/spec-config.yml`:

```yaml
canonical_spec: PROJECT_DESIGN.md
spec_version: v3
supporting_docs:
  - ARCHITECTURE.md
  - PLAN.md
operational_docs:
  - AGENTS.md
  - STYLE.md
tag_spec_map:            # optional: drives tag-based spec_refs inference
  auth: "§8.1 @ 0.85"    # files tagged `auth` → inferred ref §8.1, confidence 0.85
  worker: "§6 @ 0.75"
```

`tag_spec_map` is how tag-based inference gets its section numbers. **The `_build.py` template ships with no hardcoded tag→section mappings** — section numbers are inherently project-specific, and a baked-in map would write wrong inferred refs into every other project's codemap. No `tag_spec_map` → the script records only explicit `@spec:` annotations (the direct path may still infer by reading the spec).

When this file exists, Cartographer uses it as authoritative. When it doesn't, Cartographer picks the best candidate and tells the user:

> "No spec-config.yml found. Picked `PROJECT_DESIGN.md` as the canonical spec based on filename + section density. Other candidates: `PLAN.md`, `ARCHITECTURE.md`. Add a `.codemap/spec-config.yml` to override."

### Spec_refs extraction — explicit wins, inference fills gaps

Two ways a source file gets `spec_refs` populated:

**Explicit annotations (always win).** Comments like:
- `// @spec: §8.1`
- `# @spec: §8.1`
- `/** @spec §8.1 */`
- `// implements: §X.Y`

Cartographer extracts these directly. Explicit annotations always override inferred ones.

**Inferred spec_refs (gap-filling).** For source files without explicit annotations, Cartographer does inference *only* when the file matches one of these tag profiles (the ones audit Category 7 cares about most):
- `auth`, `security-sensitive`
- `db`, `data-model`, `schema`
- `worker`, `concurrency`
- `api` (top-level route handlers)
- `crypto`
- Any file tagged `external-api`

For each such file, Cartographer reads the canonical spec's section list plus the file's `purpose` and a small portion of its code, and decides whether it implements one or more sections. Records as `spec_refs` with a confidence score.

```json
"spec_refs": [
  { "ref": "§8.1", "source": "explicit" },
  { "ref": "§3.7", "source": "inferred", "confidence": 0.82 }
]
```

Inferred refs below confidence 0.7 are not recorded — better no inference than wrong inference.

How inference happens depends on the execution path: the **direct path** reads the canonical spec and decides per file; the **script path** only applies the project's `tag_spec_map` from `spec-config.yml` (it cannot read and reason about the spec). No map configured → script emits explicit refs only.

Full details and examples: `references/spec-extraction.md`.

### Documentation entries in structure.json

```json
"PROJECT_DESIGN.md": {
  "kind": "documentation",
  "language": "markdown",
  "loc": 1194,
  "size_bytes": 59169,
  "purpose": "Design specification for X",
  "tags": ["documentation", "spec"],
  "doc_class": "spec",
  "is_canonical_spec": true,
  "section_count": 47,
  "spec_refs": [],
  "entry_point": false,
  "test_file": false
}
```

`doc_class` enum: `spec` | `operational` | `informational`. `section_count` is the number of top-level `##` or `### \d+\.` headers — useful to audit Category 7 for understanding how much spec content exists.

## Self-refresh policy

Cartographer refreshes aggressively without asking permission. When invoked:

- **Stale codemap** (`last_refresh_commit` behind HEAD, or any file's content hash doesn't match disk): refresh affected files **automatically** and report.
- **Corrupt codemap** (schema mismatch, malformed JSON): rebuild **automatically** and report.
- **File deleted from disk but persists in codemap**: remove its entries **automatically**.
- **File appears renamed** (same content hash, different path): update the path **automatically**.

The principle: Cartographer's job is to keep the maps current. Asking permission to do that job is friction.

**Exceptions where Cartographer asks first:**
- A **full rebuild** (50+ commits stale, schema drift). Expensive enough to authorize.
- A change to the user's controlled vocabulary or schema (new domain tag, new field). These shouldn't happen silently.
- **Destructive actions outside `.codemap/`** (e.g., suggesting deletion of `*_old.ts`). Cartographer never deletes source code; it only writes to `.codemap/`.

## How other skills consume the codemap

`app-audit` Phase 3 (Execute) uses the codemap for targeted retrieval instead of grep:

- *"Find all security-sensitive files"* → query `structure.json` for `tags includes 'security-sensitive'`
- *"What implements §8.1?"* → query the `spec_refs` index in `structure.json` and `functions.json`
- *"What depends on `auth/refresh.ts`?"* → read `dependencies.json["src/auth/refresh.ts"].imported_by`
- *"Are there suspicious duplicate files?"* → read `warnings.json` directly

`audit-fix` Phase 1 (Plan) uses the codemap for blast-radius ordering:

- *File-level blast radius* → `dependencies.json[file].imported_by`
- *Function-level blast radius* → `functions.json[file].functions[fn].called_by` (requires stage 4)

When stage 4 hasn't run, `audit-fix`'s function-level tier classification silently degrades to file-level. `audit-fix` Phase 0 detects this and invokes Cartographer with `--with-call-graph` before continuing.

## Honesty about Cartographer's limits

The codemap is *Claude's understanding* of the code, written to JSON. It can be wrong:

- Wrong `purpose` (Claude misread the file)
- Wrong tags (file tagged `auth` but it's actually session management)
- Wrong inferred `spec_refs`
- Stale entries the diff-refresh missed (rare but possible)

**Hard rule for skills that consume the codemap:** the codemap directs attention but does not substitute for reading the code. When acting on codemap data — recording an audit finding, ordering a fix — re-read the actual file before recording. The codemap saves time on "which file should I look at"; it does not save time on "is this code correct."

## Reference files

- `references/codemap-schemas.md` — full JSON schemas for all five files. Read whenever writing or reading the codemap.
- `references/tag-vocabulary.md` — controlled vocabulary for tags. Read during full build when inferring tags.
- `references/entry-point-patterns.md` — patterns for legitimate entry points so they're not flagged as orphans.
- `references/extraction-by-language.md` — language-specific notes for imports, exports, and function signatures (including markdown).
- `references/spec-extraction.md` — how spec_refs are populated, both explicit and inferred.
- `references/build-stages.md` — full details on stages 1–4, the stage-4 opt-in flow, the cache-reuse policy.
- `references/_build.py` — drop-in Python build script template (script execution path).

## Standalone invocation phrases

- "Build the codemap"
- "Refresh the codemap" / "Update the maps"
- "Run cartographer"
- "What does cartographer say about X?"
- "Find duplicate files in this repo"
- "Map this codebase"

## Output format

End every Cartographer run with a brief summary:

```
Cartographer complete.
- Operation: full_build | incremental_refresh
- Files in codemap: 247
- Files refreshed this run: 14 (12 modified, 2 added, 0 deleted)
- Stages run: 1_tags, 2_spec_refs, 3_qualified_names  [+ 4_call_graph if active]
- Warnings: 6 (1 high, 3 medium, 2 low)
- Codemap location: .codemap/
- Recommended next step: review warnings.json, commit the codemap.
```

Surface any high-severity warnings inline in the summary so the user doesn't miss them.
