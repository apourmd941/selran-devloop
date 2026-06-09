# Codemap JSON Schemas

Definitive shapes for the five files Cartographer maintains in `.codemap/`. Read this whenever building or refreshing the codemap.

All files are JSON with 2-space indentation, pretty-printed for git diff readability.

---

## 1. structure.json

Hierarchical map of the codebase. Describes where files live, what they are, what they're for.

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-17T14:22:00Z",
  "root": "/path/to/Your App",
  "languages_detected": ["typescript", "rust"],
  "files_count": 247,

  "directories": {
    "src/": {
      "purpose": "Application source root",
      "files_direct": 4,
      "files_recursive": 198,
      "subdirs": ["src/auth/", "src/workers/", "src/db/", "src/ui/"]
    },
    "src/auth/": {
      "purpose": "OAuth, credential storage, refresh logic",
      "files_direct": 6,
      "files_recursive": 6,
      "subdirs": []
    }
  },

  "files": {
    "src/auth/refresh.ts": {
      "kind": "source",
      "language": "typescript",
      "loc": 142,
      "size_bytes": 4821,
      "purpose": "Exchange refresh tokens for new access token pairs",
      "tags": ["auth", "security-sensitive", "external-api", "async"],
      "spec_refs": [
        { "ref": "v3 §8.1", "source": "explicit" }
      ],
      "entry_point": false,
      "test_file": false
    },
    "src/workers/categorize.rs": {
      "kind": "source",
      "language": "rust",
      "loc": 318,
      "purpose": "Background worker that categorizes incoming messages",
      "tags": ["worker", "concurrency", "db"],
      "spec_refs": [
        { "ref": "v3 §1.3", "source": "explicit" },
        { "ref": "v3 §3.7", "source": "inferred", "confidence": 0.85 }
      ],
      "entry_point": false,
      "test_file": false
    },
    "chief-of-staff-v3-design.md": {
      "kind": "documentation",
      "language": "markdown",
      "loc": 1194,
      "size_bytes": 59169,
      "purpose": "v3 design specification — chief of staff for communication",
      "tags": ["documentation", "documentation-class:spec", "canonical-spec"],
      "doc_class": "spec",
      "is_canonical_spec": true,
      "spec_version": "v3",
      "section_count": 47,
      "spec_refs": [],
      "entry_point": false,
      "test_file": false
    },
    "AGENTS.md": {
      "kind": "documentation",
      "language": "markdown",
      "loc": 312,
      "size_bytes": 12798,
      "purpose": "Agent / skill conventions and project norms",
      "tags": ["documentation", "documentation-class:operational"],
      "doc_class": "operational",
      "section_count": 14,
      "spec_refs": [],
      "entry_point": false,
      "test_file": false
    },
    "README.md": {
      "kind": "documentation",
      "language": "markdown",
      "loc": 384,
      "size_bytes": 14261,
      "purpose": "Project README",
      "tags": ["documentation", "documentation-class:informational"],
      "doc_class": "informational",
      "section_count": 8,
      "spec_refs": [],
      "entry_point": false,
      "test_file": false
    }
  }
}
```

**Field notes:**

- `kind` enum: `source` | `test` | `config` | `documentation` | `generated` | `asset` | `other`
- `entry_point` true if this file is recognized as a legitimate entry point per `entry-point-patterns.md` (used to suppress orphan-file warnings)
- `test_file` true if path matches test conventions (`*.test.*`, `*.spec.*`, `tests/`, `test_*.py`, etc.)
- `tags` come from the controlled vocabulary in `tag-vocabulary.md`
- `spec_refs` (v0.2.1) is an array of objects, not strings. Each entry has `ref` (the section reference, e.g. `"v3 §8.1"`), `source` (`"explicit"` from a `@spec:` comment, or `"inferred"` from cartographer's content match), and (for inferred only) `confidence` 0–1. Inferred refs below confidence 0.7 are not recorded.
- `doc_class` (v0.2.1, documentation files only) enum: `spec` | `operational` | `informational`
- `is_canonical_spec` (v0.2.1, documentation files only) — true for the file designated as canonical spec by `.codemap/spec-config.yml` or by cartographer's best-guess heuristic
- `spec_version` (v0.2.1, documentation files only) — extracted from filename, title, or explicit `version:` markers (e.g., `"v3"`)
- `section_count` (v0.2.1, documentation files only) — number of top-level `##` or `### \d+\.` headers; shallow extraction for audit awareness

**Migration from v0.2.0 spec_refs format:** v0.2.0 used `spec_refs: ["v3 §8.1"]` (plain strings). v0.2.1 uses `spec_refs: [{"ref": "v3 §8.1", "source": "explicit"}]` (objects). On upgrade, existing v0.2.0 string entries are converted to `{"ref": <string>, "source": "explicit"}` — we assume any pre-existing spec_ref was explicit (developer-supplied via comments or manual edit).

---

## 2. dependencies.json

What each file imports and what imports it. Plus external (npm/cargo/pip) dependencies.

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-17T14:22:00Z",

  "graph": {
    "src/auth/refresh.ts": {
      "imports_from": [
        {
          "path": "src/auth/store.ts",
          "symbols": ["saveTokens", "loadTokens"],
          "kind": "named"
        },
        {
          "path": "src/logging/logger.ts",
          "symbols": ["logger"],
          "kind": "named"
        }
      ],
      "imported_by": [
        {
          "path": "src/workers/sync.ts",
          "symbols": ["refreshToken"],
          "kind": "named"
        }
      ],
      "external_dependencies": [
        { "name": "node-fetch", "version_constraint": "^3.3.0" },
        { "name": "zod", "version_constraint": "^3.22.0" }
      ]
    }
  }
}
```

**Field notes:**

- `kind` enum for import edges: `named` (named imports) | `default` (default import) | `namespace` (e.g., `import * as foo`) | `side_effect` (e.g., `import './setup'`) | `dynamic` (runtime import())
- `symbols` are the actual symbol names — empty array for side-effect imports
- `imports_from` and `imported_by` must be consistent: for every `imports_from` edge A→B, there must be a corresponding `imported_by` entry on B pointing back to A
- `external_dependencies` lists package-manager dependencies actually used by this file (not the full project's package.json)

---

## 3. functions.json

Function-level details. The finest grain.

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-17T14:22:00Z",

  "files": {
    "src/auth/refresh.ts": {
      "functions": [
        {
          "name": "refreshToken",
          "qualified_name": "src/auth/refresh.ts::refreshToken",
          "signature": "async (accountId: string) => Promise<TokenPair>",
          "loc_range": [42, 78],
          "purpose": "Exchange a stored refresh token for a new access/refresh pair",
          "calls": [
            "logger.error",
            "store.loadTokens",
            "store.saveTokens",
            "fetch"
          ],
          "called_by": [
            "src/workers/sync.ts::syncAccount"
          ],
          "tags": ["security-sensitive", "external-api", "async"],
          "spec_refs": [{ "ref": "v3 §8.1", "source": "explicit" }],
          "exported": true,
          "last_modified_commit": "abc123def"
        },
        {
          "name": "isExpired",
          "qualified_name": "src/auth/refresh.ts::isExpired",
          "signature": "(token: AccessToken) => boolean",
          "loc_range": [82, 91],
          "purpose": "Check whether an access token has expired",
          "calls": [],
          "called_by": ["src/auth/refresh.ts::refreshToken"],
          "tags": ["pure"],
          "spec_refs": [],
          "exported": false,
          "last_modified_commit": "abc003"
        }
      ]
    }
  }
}
```

**Field notes:**

- `qualified_name` is the unique identifier: `<file path>::<function name>`. For methods on classes/structs: `<file>::<TypeName>.<methodName>`. For nested or anonymous functions, include parent scope: `<file>::<outerFn>::<innerFn>`.
- `calls` lists function references made inside this function's body. Resolution is best-effort — when ambiguous, use the symbol name as written (e.g., `store.saveTokens`) and let consumers resolve.
- `called_by` is the inverse, populated when cross-references are built
- `signature` is the function's parameter list and return type, formatted in the language's idiom (TS arrow function syntax, Rust fn signature, Python def line, etc.)
- `loc_range` is `[start_line, end_line]` inclusive
- `tags` come from `tag-vocabulary.md`, applied at function granularity (a file can be untagged while a specific function in it is `security-sensitive`)

**v0.3.0 — when these fields are populated:**

Prior to v0.3.0, several function-level fields were defined in the schema but typically empty. v0.3.0 populates them via four build stages:

- `tags` (Stage 1, default-on) — inherited from the file's tags at extraction time
- `spec_refs` (Stage 2, default-on) — inherited from the file's spec_refs plus a scan of the 4 comment lines above the signature for `§N.M` patterns
- `qualified_name` and `last_modified_commit` (Stage 3, default-on) — `qualified_name` built from file path + module/struct context; `last_modified_commit` from `git log -1` per file
- `calls` and `called_by` (Stage 4, opt-in) — regex-based identifier matching across function bodies with stdlib filtering; precision approximately 70–85%; user is prompted before this stage runs

When Stage 4 has not run, `calls` and `called_by` remain empty across all functions (not partially populated). Consumers can check `build_metadata.stages_run` in functions.json to see which stages were active.

For full details on the four stages, see `build-stages.md`.

---

## 4. warnings.json

Detector output. The "running stale code" prevention layer.

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-17T14:22:00Z",
  "summary": {
    "high": 1,
    "medium": 3,
    "low": 2,
    "total": 6
  },

  "duplicate_basenames": [
    {
      "basename": "auth.ts",
      "locations": [
        "src/auth/auth.ts",
        "src/legacy/auth.ts"
      ],
      "severity": "high",
      "concern": "Two files named auth.ts; imports may resolve unpredictably depending on tsconfig paths and the build's module resolution. Running app may load a different version than expected.",
      "suggested_action": "Rename one (e.g., legacy/legacy_auth.ts), or remove the legacy copy if it's unused."
    }
  ],

  "suspicious_names": [
    {
      "path": "src/components/Dashboard.old.tsx",
      "pattern": "*.old.*",
      "severity": "medium",
      "concern": "Filename signals stale backup. Verify it's not still imported anywhere and remove.",
      "imported_by_count": 0
    }
  ],

  "backup_directories": [
    {
      "path": "src_backup_2026_04_12/",
      "severity": "high",
      "concern": "Backup directory in source tree. Likely in the build path; may shadow current source.",
      "suggested_action": "Move outside source tree or add to .gitignore."
    }
  ],

  "orphan_files": [
    {
      "path": "src/auth/refresh_old.ts",
      "severity": "medium",
      "concern": "Source file with no imported_by entries. Likely dead code from an incomplete refactor.",
      "is_entry_point": false,
      "suggested_action": "Remove or archive outside the source tree."
    }
  ],

  "near_duplicates": [
    {
      "files": ["src/auth/refresh.ts", "src/auth/refresh_v2.ts"],
      "similarity": 0.87,
      "severity": "high",
      "concern": "Two files are ~87% identical. Almost certainly an unfinished refactor where one is canonical and the other is stale.",
      "suggested_action": "Determine which is the running version (check imports), keep that one, remove the other."
    }
  ],

  "stale_build_output": [
    {
      "compiled_path": "dist/auth/refresh.js",
      "source_path": "src/auth/refresh.ts",
      "compiled_mtime": "2026-05-15T10:00:00Z",
      "source_mtime": "2026-05-17T13:45:00Z",
      "severity": "medium",
      "concern": "Compiled output is older than source. Running app may serve stale behavior.",
      "suggested_action": "Re-run the build before running the app."
    }
  ],

  "canonical_designations": [
    {
      "cluster": ["src/auth/refresh.ts", "src/auth/refresh_v2.ts"],
      "canonical": "src/auth/refresh.ts",
      "stale_candidates": ["src/auth/refresh_v2.ts"],
      "designation_reason": "import_graph_reachability",
      "concern": "src/auth/refresh.ts is imported by src/workers/sync.ts; refresh_v2.ts has no imported_by entries.",
      "severity": "high",
      "suggested_action": "Remove src/auth/refresh_v2.ts or archive it outside the source tree."
    }
  ]
}
```

**Field notes:**

- `severity` enum: `high` | `medium` | `low` — matches the audit skill's severity definitions
- Each warning category is its own array, may be empty. Always include all seven categories in the output (use `[]` if empty) so consumers know the detector ran.
- `summary` at the top totals warnings across all categories for at-a-glance reading
- `suggested_action` is a one-liner; never a multi-step plan (that's the user's call)
- `canonical_designations.designation_reason` enum: `import_graph_reachability` | `most_recent_commit` | `loc_and_naming` | `alphabetical_tiebreak` | `ambiguous`
- When `designation_reason` is `ambiguous` or `alphabetical_tiebreak`, severity must be `high` — these are the cases most likely to produce "running stale code" failures because *nobody* knows which version is current. Near-duplicate-derived clusters are also `high` regardless of reason.
- `warnings.json` also carries `detectors_run` (which detectors actually executed this build) and `codemap_drift` (drift events app-audit appends in its Phase 0.5.6; preserved across refreshes while the affected file is unchanged).

---

## 5. state.json

Internal bookkeeping. Not for human consumption directly; used by Cartographer's refresh logic and by skills that need to know if the codemap is fresh.

```json
{
  "schema_version": 2,
  "cartographer_version": "0.5.0",
  "created_at": "2026-05-10T09:00:00Z",
  "last_full_build_at": "2026-05-10T09:00:00Z",
  "last_full_build_commit": "abc123def",
  "last_refresh_at": "2026-05-17T14:22:00Z",
  "last_refresh_commit": "ghi789jkl",
  "spec_config_hash": "9f2c4ab1e0d83a77",
  "build_metadata": {
    "files_processed": 247,
    "files_analyzed": 12,
    "files_reused": 235,
    "languages_detected": ["typescript", "rust"],
    "build_method": "py-script-richer",
    "stages_run": ["1_tags", "2_spec_refs", "3_qualified_names"]
  },
  "capabilities": {
    "incremental_refresh": true,
    "respects_gitignore": true,
    "function_extraction_languages": ["rust", "python", "typescript", "javascript"],
    "import_extraction_languages": ["rust", "python", "typescript", "javascript"],
    "import_resolution": "best-effort-static",
    "detectors_run": ["duplicate_basenames", "suspicious_names", "backup_directories",
                      "orphan_files", "near_duplicates", "stale_build_output",
                      "canonical_designations"],
    "call_graph": "regex-best-effort (stage 4, opt-in)"
  },
  "per_file_state": {
    "src/auth/refresh.ts": {
      "content_hash": "sha256:a3f5...",
      "last_commit": "ghi789jkl",
      "last_commit_ts": 1747500300
    },
    "src/workers/categorize.rs": {
      "content_hash": "sha256:b2c8...",
      "last_commit": "def456",
      "last_commit_ts": 1747033860
    }
  }
}
```

**Field notes:**

- `content_hash` is SHA-256 of the file contents. The incremental-refresh key: a file whose on-disk hash matches its entry reuses its prior analysis; a mismatch (including uncommitted edits) triggers re-analysis.
- `last_full_build_commit` is the SHA at which a full rebuild was last performed. Incremental refreshes don't update this; only full rebuilds do.
- `last_refresh_commit` is the most recent commit at which any refresh (full or incremental) ran.
- `cartographer_version` allows future Cartographer versions to detect incompatible schemas and trigger a rebuild. The script auto-triggers a full rebuild on any mismatch with its own version.
- `capabilities` is the **honesty contract**: exactly what this build produced. Consumers (app-audit, audit-fix) must check it before trusting a field — a detector absent from `detectors_run` means its warnings array is "not checked," not "verified empty."
- `last_commit` / `last_commit_ts` are the file's most recent git commit (hash, unix time), used by detector 7's most-recent-commit designation.
- `spec_config_hash` detects spec-config.yml changes — a mismatch forces docs and spec_refs re-analysis even for unchanged files.

---

## Consistency invariants

When writing or refreshing, Cartographer must maintain these invariants. Other skills can rely on them:

1. **Cross-reference symmetry.** Every `imports_from` edge in `dependencies.json` has a matching `imported_by` entry on the target. Every `calls` entry in `functions.json` has a matching `called_by` entry (when both functions are in the codemap).

2. **File presence symmetry.** Every file in `structure.json.files` has a corresponding entry in `dependencies.json.graph` (even if it has zero imports/imports_by — empty arrays are valid). Functions-level data may be absent for non-source files; for source files, an entry must exist even if `functions` is empty.

3. **Path normalization.** All paths are relative to `state.json.root`, use forward slashes, no leading `./`. Directory paths end with `/`; file paths don't.

4. **Sort order.** Within JSON arrays, sort by path (then by name for functions) so git diffs are minimal and review is predictable.

5. **State.json freshness.** After any refresh, every file in `structure.json.files` has an entry in `state.json.per_file_state`. Stale entries (for files that no longer exist) are removed.

6. **Stage 4 consistency (v0.3.0).** Either both `calls` and `called_by` are populated across all functions (Stage 4 ran), or both are empty across all functions (Stage 4 didn't run). Partial population is invalid — a future run should rebuild the cache.

If any of these invariants would be violated by a partial refresh (e.g., a cross-reference patch failed), Cartographer should report it as an error and recommend a full rebuild.
