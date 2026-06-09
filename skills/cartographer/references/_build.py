#!/usr/bin/env python3
"""
Cartographer build script (template — v0.5.0).

Copy this into a project's `.codemap/_build.py`. Walks the source tree and
writes the codemap JSON files into `.codemap/`. Used for both initial full
build and incremental refresh (content-hash-keyed; unchanged files reuse
their prior analysis, so only changed files pay extraction + git-log cost).

Invoked by:
  - User: `python3 .codemap/_build.py` from the repo root.
  - SessionStart hook (see `.claude/settings.json`): runs automatically
    on every Claude session start so the codemap stays fresh.
  - app-audit's Phase 0.5: invokes this script before audit runs.
  - audit-fix's Phase 0: invokes with --with-call-graph for tier classification.

Build stages:
  Stage 1 — Function-level tag propagation (default on)
  Stage 2 — Function-level spec_refs propagation (default on)
  Stage 3 — Qualified names + git blame per file (default on)
  Stage 4 — Call graph extraction (opt-in; --with-call-graph or interactive prompt)

Flags:
  --with-call-graph       run stage 4 (call graph extraction)
  --no-call-graph         skip stage 4 even if cached result exists
  --rebuild-call-graph    force-rebuild stage 4 cache
  --non-interactive       never prompt; treat stage 4 as off unless --with-call-graph
  --full                  ignore prior state; full rebuild

What this script can and cannot do (honesty contract):
  state.json.capabilities records exactly which detectors ran and which
  languages got function/import extraction. Consumers (app-audit, audit-fix)
  MUST read capabilities and fall back to inline analysis for anything not
  listed. Import resolution and the stage-4 call graph are best-effort
  static analysis — good enough for blast-radius grading and warning
  detection, not for precise refactoring.

Per-project customization:
  Tag inference (infer_tags) ships with a GENERIC baseline. Project-specific
  tags and the tag→spec-section map belong in `.codemap/spec-config.yml`
  (see `tag_spec_map` below), NOT hardcoded here — that keeps this template
  portable across projects.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CODEMAP_DIR = REPO_ROOT / ".codemap"
CALL_GRAPH_CACHE = CODEMAP_DIR / "_call_graph_cache.json"
CARTOGRAPHER_VERSION = "0.5.0"
STATE_SCHEMA_VERSION = 2

# Directories that never get walked into.
# `.claude` is excluded so cartographer never descends into Desktop-dispatched
# code-task worktrees (.claude/worktrees/<name>/), which are full copies of the
# repo and would otherwise double-count every file as a duplicate.
SKIP_DIRS = {
    ".git", "target", "node_modules", "dist", ".next", "build", "out",
    "__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".codemap", ".claude", "coverage", ".turbo",
}

# Build-output directories detector 6 inspects directly (they are excluded
# from the main walk). `target/` is omitted — cargo manages its own staleness.
BUILD_OUTPUT_DIRS = ["dist", "build", ".next", "out"]

# File suffixes worth analyzing.
SOURCE_SUFFIXES = {".rs", ".py", ".sh", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".sql"}
CONFIG_SUFFIXES = {".toml", ".yaml", ".yml", ".json"}
DOC_SUFFIXES = {".md", ".mdx", ".rst", ".txt"}
HTML_SUFFIXES = {".html"}

# Filenames that signal an entry point regardless of import graph.
ENTRY_POINT_NAMES = {
    "main.rs", "lib.rs", "build.rs",
    "main.py", "__main__.py", "app.py", "cli.py", "setup.py", "conftest.py",
    "index.html", "index.js", "index.ts", "main.ts", "main.js",
    "server.ts", "server.js",
    "Cargo.toml", "package.json", "tauri.conf.json",
    "vite.config.ts", "next.config.js", "next.config.mjs",
}

# Basenames that are duplicated BY CONVENTION — never flag these as
# duplicate-basename warnings (every Rust crate has a mod.rs, every Python
# package an __init__.py, every Next.js route a page.tsx, ...).
CONVENTIONAL_BASENAMES = {
    "mod.rs", "lib.rs", "main.rs", "build.rs",
    "__init__.py", "__main__.py", "conftest.py", "setup.py",
    "index.ts", "index.tsx", "index.js", "index.jsx", "index.html",
    "page.tsx", "layout.tsx", "route.ts", "error.tsx", "loading.tsx",
    "types.ts", "main.py",
    "README.md", "CHANGELOG.md", "LICENSE", "Makefile", "Dockerfile",
    "Cargo.toml", "package.json", "tsconfig.json", ".gitignore",
    "AGENTS.md", "CLAUDE.md", "SKILL.md",
}

# Suspicious filename patterns for warnings.json detector 2.
SUSPICIOUS_PATTERNS = [
    (re.compile(r".*\.old\..*", re.IGNORECASE),         "*.old.*"),
    (re.compile(r".*\.backup\..*", re.IGNORECASE),       "*.backup.*"),
    (re.compile(r".*\.bak$|.*\.bak\..*", re.IGNORECASE), "*.bak.*"),
    (re.compile(r".*_old\..*"),                          "*_old.*"),
    (re.compile(r".*_backup\..*"),                       "*_backup.*"),
    (re.compile(r".*_archive\..*"),                      "*_archive.*"),
    (re.compile(r".*_v\d+\..*"),                         "*_v[N].*"),
    (re.compile(r".*[-_]copy\..*|.*Copy\..*", re.IGNORECASE), "*-copy.*"),
    (re.compile(r".*(DELETE|REMOVE|TODO_REMOVE).*"),     "*DELETE/REMOVE*"),
    (re.compile(r"^(Untitled|New File)\..*"),            "Untitled.*"),
]

# Backup-directory patterns for detector 3 (matched against dir basenames).
BACKUP_DIR_PATTERNS = [
    (re.compile(r".*_backup.*", re.IGNORECASE), "*_backup*"),
    (re.compile(r".*_archive.*", re.IGNORECASE), "*_archive*"),
    (re.compile(r".*_old$", re.IGNORECASE),      "*_old"),
    (re.compile(r"^OLD_.*"),                     "OLD_*"),
    (re.compile(r"^BACKUP_.*"),                  "BACKUP_*"),
    (re.compile(r"^ARCHIVE_.*"),                 "ARCHIVE_*"),
    (re.compile(r".*_\d{4}_\d{2}_\d{2}$"),       "*_YYYY_MM_DD"),
    (re.compile(r".*_\d{8}$"),                   "*_YYYYMMDD"),
]

# Directories where the _v[N] suffix is canonical (sequenced), not a backup.
MIGRATION_DIRS = {"migrations", "migration"}

FN_SIG_RE = re.compile(
    r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?(?:const\s+)?fn\s+([a-zA-Z_][a-zA-Z0-9_]*)"
)
PY_DEF_RE = re.compile(r"^(\s*)(?:async\s+)?def\s+([a-zA-Z_]\w*)\s*\(")
TS_FN_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)"
)
TS_ARROW_RE = re.compile(
    r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::[^=]*)?=\s*(?:async\s+)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
)

RUST_USE_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?use\s+([a-zA-Z0-9_:]+(?:::\{[^}]+\})?)\s*;")
RUST_MOD_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*;")
PY_IMPORT_RE = re.compile(r"^\s*import\s+([\w\.]+(?:\s*,\s*[\w\.]+)*)")
PY_FROM_RE = re.compile(r"^\s*from\s+(\.*[\w\.]*)\s+import\s+(.+)")
TS_IMPORT_RES = [
    re.compile(r"""(?:import|export)\s+[^'"]*?\bfrom\s+['"]([^'"]+)['"]"""),
    re.compile(r"""^\s*import\s+['"]([^'"]+)['"]"""),
    re.compile(r"""\brequire\(\s*['"]([^'"]+)['"]\s*\)"""),
]

# Section header pattern in markdown / comments — captures §N.M references.
SPEC_REF_RE = re.compile(r"§(\d+(?:\.\d+)*)")

SPEC_DOC_NAME_RE = re.compile(
    r"(DESIGN|SPEC|PLAN|ROADMAP|ARCHITECTURE)", re.IGNORECASE
)


# ---------------------------------------------------------------------
# Tag inference — GENERIC baseline only.
# Project-specific tags belong in spec-config.yml / a project's own copy.
# ---------------------------------------------------------------------

def infer_tags(rel_path: str, language: str) -> list[str]:
    """Heuristic tag inference. Conservative — better fewer correct
    tags than many wrong ones. Generic vocabulary only; see
    references/tag-vocabulary.md."""
    tags: list[str] = []
    rl = rel_path.lower()
    name = posixpath.basename(rl)

    if language == "rust":
        tags.append("rust")
    elif language in {"javascript", "typescript"}:
        tags.append("frontend")
    elif language == "sql":
        tags.append("db")

    if is_test_file(rel_path):
        tags.append("test")
    if "/migrations/" in rl or rl.startswith("migrations/"):
        tags.append("migration")
        if "db" not in tags:
            tags.append("db")
    if "/routes/" in rl or rl.startswith("routes/") or "/handlers/" in rl or "/controllers/" in rl or "/api/" in rl:
        tags.append("api")
    if "oauth" in rl or "/auth/" in rl or "_auth" in name or name.startswith("auth"):
        tags.append("auth")
    if any(k in rl for k in ("crypto", "encrypt", "keychain", "secret", "password", "credential")):
        tags.append("security-sensitive")
    if any(k in rl for k in ("worker", "scheduler", "queue", "cron", "daemon", "supervisor")):
        tags.append("worker")
    if any(k in rl for k in ("/db/", "/models/", "/schema/", "repository", "/dao/")) or "schema" in name:
        if "db" not in tags:
            tags.append("db")
    if any(k in rl for k in ("/components/", "/views/", "/pages/", "/screens/", "/ui/")):
        tags.append("ui")
    if any(k in rl for k in ("webhook", "http_client", "api_client", "/providers/", "/clients/")):
        tags.append("external-api")
    if "config" in name or "settings" in name:
        tags.append("config")

    return tags


def is_test_file(rel_path: str) -> bool:
    rl = rel_path.lower()
    name = posixpath.basename(rl)
    return (
        "/tests/" in rl or rl.startswith("tests/") or "/__tests__/" in rl
        or name.startswith("test_")
        or any(name.endswith(s) for s in (
            "_test.rs", "_test.py", ".test.ts", ".spec.ts", ".test.tsx",
            ".spec.tsx", ".test.js", ".spec.js",
        ))
    )


# ---------------------------------------------------------------------
# Documentation classification
# ---------------------------------------------------------------------

def classify_doc(rel_path: str, content: str, spec_cfg: dict) -> str:
    """Classify a markdown doc as spec / operational / informational.
    spec-config.yml is authoritative; filename + section-density patterns
    are the fallback."""
    if rel_path == spec_cfg.get("canonical_spec"):
        return "spec"
    if rel_path in spec_cfg.get("supporting_docs", []):
        return "spec"
    if rel_path in spec_cfg.get("operational_docs", []):
        return "operational"
    name = posixpath.basename(rel_path)
    if SPEC_DOC_NAME_RE.search(name) and name.lower().endswith((".md", ".mdx")):
        return "spec"
    if name in {"AGENTS.md", "CONTRIBUTING.md", "STYLE.md", "UI_DESIGN_PRINCIPLES.md", "CLAUDE.md"}:
        return "operational"
    # 3+ spec-style section markers → spec class
    markers = len(SPEC_REF_RE.findall(content)) + len(re.findall(r"^###?\s+\d+\.\d+", content, re.MULTILINE))
    if markers >= 3:
        return "spec"
    return "informational"


def section_count_in(md_content: str) -> int:
    """Top-level `## ` headers plus numbered `### N.` headers (per schema docs)."""
    n = 0
    for ln in md_content.split("\n"):
        if ln.startswith("## ") or re.match(r"^### \d+\.", ln):
            n += 1
    return n


# ---------------------------------------------------------------------
# Spec-refs inference (Stage 2 helper)
# ---------------------------------------------------------------------

def infer_file_spec_refs(rel_path: str, text: str, tags: list[str], spec_cfg: dict) -> list[dict]:
    """Infer which spec sections this file likely implements.

    Returns a list of {ref, source, confidence} entries.

    Explicit §N.M references in the file are always recorded (confidence 1.0).
    Tag-based inference uses ONLY the project's spec-config.yml `tag_spec_map`
    — the template ships no hardcoded section numbers, because those are
    inherently project-specific and wrong everywhere else.
    """
    refs = []
    seen_refs = set()

    # 1. Explicit references in code comments (highest confidence)
    for match in SPEC_REF_RE.finditer(text):
        ref = match.group(1)
        if ref not in seen_refs:
            refs.append({"ref": f"§{ref}", "source": "explicit", "confidence": 1.0})
            seen_refs.add(ref)

    # 2. Tag-based inference from spec-config.yml tag_spec_map, e.g.:
    #      tag_spec_map:
    #        auth: "§8.1 @ 0.85"
    #        worker: "§6 @ 0.75"
    tag_map = spec_cfg.get("tag_spec_map", {})
    if isinstance(tag_map, dict):
        for tag in tags:
            entry = tag_map.get(tag)
            if not entry:
                continue
            m = re.match(r"§?([\d\.]+)\s*(?:@\s*([\d\.]+))?", str(entry).strip())
            if not m:
                continue
            ref_key = m.group(1)
            conf = float(m.group(2)) if m.group(2) else 0.75
            if conf < 0.7:
                continue  # below recording threshold — better no inference than wrong
            if ref_key not in seen_refs:
                refs.append({"ref": f"§{ref_key}", "source": "inferred", "confidence": conf})
                seen_refs.add(ref_key)

    return refs


# ---------------------------------------------------------------------
# Qualified name computation (Stage 3 helper)
# ---------------------------------------------------------------------

def compute_qualified_prefix(rel_path: str, language: str) -> str:
    """Build a module-path prefix for functions defined in this file."""
    p = Path(rel_path)
    parts = list(p.parts)
    stem = p.stem

    if language == "rust":
        if "src" in parts:
            src_idx = parts.index("src")
            crate = "::".join(parts[:src_idx])
            module = "::".join(parts[src_idx + 1:-1] + ([stem] if stem not in ("lib", "mod", "main") else []))
            return f"{crate}::{module}" if module else crate
        return "::".join(parts[:-1] + [stem])

    if language == "python":
        mods = parts[:-1] + ([stem] if stem != "__init__" else [])
        return ".".join(mods)

    if language in {"javascript", "typescript"}:
        return str(p.with_suffix(""))

    return rel_path


# ---------------------------------------------------------------------
# Git helpers (Stage 3) — per file, skipped for unchanged files on refresh
# ---------------------------------------------------------------------

def file_last_commit(rel_path: str) -> tuple[str, int]:
    """Returns (commit_hash, commit_unix_ts) of the file's last commit,
    or ("", 0) on failure / non-git environments."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H %ct", "--", rel_path],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split()
            if len(parts) == 2:
                return parts[0], int(parts[1])
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
        pass
    return "", 0


def git_head() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return ""


def git_dirty() -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
        )
        return bool(result.stdout.strip()) if result.returncode == 0 else False
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


# ---------------------------------------------------------------------
# Import extraction + resolution (per language, best-effort static)
# ---------------------------------------------------------------------

def extract_rust_imports(text: str) -> list[dict]:
    """Extract Rust use-statements and mod declarations (single-line only)."""
    imports = []
    for line in text.split("\n"):
        m = RUST_USE_RE.match(line)
        if m:
            raw = m.group(1)
            path = raw.split("::{")[0]
            symbols_part = raw.split("::{", 1)[1].rstrip("}") if "::{" in raw else ""
            symbols = [s.strip() for s in symbols_part.split(",")] if symbols_part else []
            imports.append({"path": path, "symbols": symbols, "kind": "use"})
            continue
        m = RUST_MOD_RE.match(line)
        if m:
            imports.append({"path": m.group(1), "symbols": [], "kind": "mod"})
    return imports


def extract_python_imports(text: str) -> list[dict]:
    imports = []
    for line in text.split("\n"):
        m = PY_IMPORT_RE.match(line)
        if m:
            for mod in m.group(1).split(","):
                imports.append({"path": mod.strip(), "symbols": [], "kind": "import"})
            continue
        m = PY_FROM_RE.match(line)
        if m:
            symbols = [s.strip().split(" as ")[0] for s in m.group(2).split(",") if s.strip() != "("]
            imports.append({"path": m.group(1), "symbols": symbols, "kind": "from"})
    return imports


def extract_ts_imports(text: str) -> list[dict]:
    imports = []
    seen = set()
    for line in text.split("\n"):
        for pat in TS_IMPORT_RES:
            for m in pat.finditer(line):
                spec = m.group(1)
                if spec not in seen:
                    imports.append({"path": spec, "symbols": [], "kind": "import"})
                    seen.add(spec)
    return imports


def build_rust_module_index(rust_files: list[str]) -> dict:
    """Index (crate, module-segments) → rel path, for resolving use-paths."""
    index: dict[tuple, str] = {}
    for rel in rust_files:
        parts = list(Path(rel).parts)
        if "src" in parts:
            i = parts.index("src")
            crate = "/".join(parts[:i]) or "."
            mods = parts[i + 1:]
        else:
            crate = "."
            mods = parts
        stem = Path(mods[-1]).stem
        mods = mods[:-1]
        if stem not in ("lib", "main", "mod"):
            mods = mods + [stem]
        index[(crate, tuple(mods))] = rel
    return index


def rust_file_context(rel: str) -> tuple[str, tuple]:
    """(crate, module-segments) for the importing file itself."""
    parts = list(Path(rel).parts)
    if "src" in parts:
        i = parts.index("src")
        crate = "/".join(parts[:i]) or "."
        mods = parts[i + 1:]
    else:
        crate = "."
        mods = parts
    stem = Path(mods[-1]).stem
    mods = mods[:-1]
    if stem not in ("lib", "main", "mod"):
        mods = mods + [stem]
    return crate, tuple(mods)


def resolve_rust_import(imp: dict, importer_rel: str, index: dict, all_files: set) -> str | None:
    crate, importer_mods = rust_file_context(importer_rel)

    if imp["kind"] == "mod":
        # `mod foo;` → sibling foo.rs or foo/mod.rs
        d = posixpath.dirname(importer_rel)
        for cand in (f"{d}/{imp['path']}.rs", f"{d}/{imp['path']}/mod.rs"):
            cand = posixpath.normpath(cand)
            if cand in all_files:
                return cand
        return None

    toks = imp["path"].split("::")
    if toks[0] == "crate":
        base: list = []
        toks = toks[1:]
    elif toks[0] == "self":
        base = list(importer_mods)
        toks = toks[1:]
    elif toks[0] == "super":
        base = list(importer_mods)
        while toks and toks[0] == "super":
            toks = toks[1:]
            base = base[:-1]
    else:
        base = []  # external crate, or bare top-level module of this crate

    full = base + toks
    # Longest-prefix match: the use path may end in an item, not a module.
    for k in range(len(full), 0, -1):
        hit = index.get((crate, tuple(full[:k])))
        if hit and hit != importer_rel:
            return hit
    return None


def resolve_python_import(imp: dict, importer_rel: str, all_files: set) -> str | None:
    raw = imp["path"]
    candidates: list[str] = []

    if raw.startswith("."):
        dots = len(raw) - len(raw.lstrip("."))
        modpath = raw.lstrip(".")
        base = posixpath.dirname(importer_rel)
        for _ in range(dots - 1):
            base = posixpath.dirname(base)
        parts = modpath.split(".") if modpath else []
        stem = "/".join([base] + parts) if base else "/".join(parts)
        candidates += [f"{stem}.py", f"{stem}/__init__.py"]
        for sym in imp.get("symbols", []):
            candidates += [f"{stem}/{sym}.py"]
    else:
        parts = raw.split(".")
        for root in ("", "src/"):
            stem = root + "/".join(parts)
            candidates += [f"{stem}.py", f"{stem}/__init__.py"]
            for sym in imp.get("symbols", []):
                candidates += [f"{stem}/{sym}.py"]
        d = posixpath.dirname(importer_rel)
        if d:
            stem = f"{d}/" + "/".join(parts)
            candidates += [f"{stem}.py", f"{stem}/__init__.py"]

    for c in candidates:
        c = posixpath.normpath(c)
        if c in all_files and c != importer_rel:
            return c
    return None


def resolve_ts_import(imp: dict, importer_rel: str, all_files: set) -> str | None:
    spec = imp["path"]
    if not spec.startswith("."):
        return None  # package import — recorded but not resolved to a file
    base = posixpath.normpath(posixpath.join(posixpath.dirname(importer_rel), spec))
    candidates = [base] if "." in posixpath.basename(base) else []
    for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        candidates.append(base + ext)
    for ext in (".ts", ".tsx", ".js", ".jsx"):
        candidates.append(f"{base}/index{ext}")
    for c in candidates:
        if c in all_files and c != importer_rel:
            return c
    return None


# ---------------------------------------------------------------------
# Function extraction (stages 1, 2, 3 inline) — Rust, Python, TS/JS
# ---------------------------------------------------------------------

def make_fn_entry(name: str, signature: str, start: int, *, qualified_prefix: str,
                  sep: str, file_tags: list[dict], file_spec_refs: list[dict],
                  exported: bool, file_last_commit_hash: str) -> dict:
    return {
        "name": name,
        "qualified_name": f"{qualified_prefix}{sep}{name}" if qualified_prefix else name,
        "signature": signature,
        "loc_range": [start, 0],  # end filled by finalize_loc_ranges
        "calls": [],
        "called_by": [],
        "tags": list(file_tags),          # Stage 1
        "spec_refs": list(file_spec_refs),  # Stage 2 (nearby refs added later)
        "exported": exported,
        "last_modified_commit": file_last_commit_hash,  # Stage 3
    }


def extract_rust_functions(text: str, **kw) -> list[dict]:
    fns: list[dict] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = FN_SIG_RE.match(lines[i])
        if not m:
            i += 1
            continue
        start = i + 1
        buf = lines[i].rstrip()
        j = i
        while j < len(lines) and "{" not in lines[j] and not lines[j].rstrip().endswith(";"):
            j += 1
            if j < len(lines):
                buf += " " + lines[j].strip()
        if "{" in buf:
            buf = buf[: buf.index("{")]
        sig = buf.strip().rstrip(";").rstrip()
        fns.append(make_fn_entry(
            m.group(1), sig, start, sep="::",
            exported=sig.lstrip().startswith("pub"), **kw,
        ))
        i = j + 1
    return fns


def extract_python_functions(text: str, **kw) -> list[dict]:
    fns: list[dict] = []
    for i, line in enumerate(text.split("\n")):
        m = PY_DEF_RE.match(line)
        if not m:
            continue
        indent, name = m.group(1), m.group(2)
        fns.append(make_fn_entry(
            name, line.strip().rstrip(":"), i + 1, sep=".",
            exported=(indent == "" and not name.startswith("_")), **kw,
        ))
    return fns


def extract_ts_functions(text: str, **kw) -> list[dict]:
    fns: list[dict] = []
    for i, line in enumerate(text.split("\n")):
        m = TS_FN_RE.match(line) or TS_ARROW_RE.match(line)
        if not m:
            continue
        fns.append(make_fn_entry(
            m.group(1), line.strip().rstrip("{").strip(), i + 1, sep=".",
            exported="export" in line, **kw,
        ))
    return fns


def attach_nearby_spec_refs(fns: list[dict], lines: list[str]) -> None:
    """Stage 2 (continued): scan the 4 comment lines above each function
    for §N.M references; explicit refs found there are appended."""
    for fn in fns:
        start_idx = fn["loc_range"][0] - 1
        seen = {r["ref"].lstrip("§") for r in fn["spec_refs"]}
        for k in range(max(0, start_idx - 4), start_idx):
            for ref_match in SPEC_REF_RE.finditer(lines[k]):
                ref = ref_match.group(1)
                if ref not in seen:
                    fn["spec_refs"].append({"ref": f"§{ref}", "source": "explicit", "confidence": 1.0})
                    seen.add(ref)


def finalize_loc_ranges(fns: list[dict], total_lines: int) -> None:
    """Set each function's loc_range end to the line before the next
    function's start (or EOF). Approximate — items between functions get
    attributed to the preceding one — but good enough for line→function
    mapping and stage-4 body bounding."""
    ordered = sorted(fns, key=lambda f: f["loc_range"][0])
    for i, fn in enumerate(ordered):
        end = ordered[i + 1]["loc_range"][0] - 1 if i + 1 < len(ordered) else total_lines
        fn["loc_range"][1] = max(fn["loc_range"][0], end)


# ---------------------------------------------------------------------
# Stage 4 — Call graph extraction (opt-in)
# ---------------------------------------------------------------------

# Names too common to produce useful edges (keywords, stdlib, builtins).
SKIP_NAMES = {
    "new", "as", "from", "into", "to_string", "clone", "unwrap", "expect",
    "ok", "err", "some", "none", "iter", "map", "filter", "collect", "len",
    "push", "pop", "insert", "remove", "get", "set", "default", "fmt",
    "drop", "build", "with", "fn", "let", "if", "else", "match", "for",
    "while", "loop", "return", "break", "continue", "use", "mod", "pub",
    "self", "true", "false", "vec", "matches", "todo", "unimplemented",
    "panic", "debug_assert", "assert", "trace", "info", "warn", "error",
    "println", "print", "format", "write", "writeln",
    # python / js builtins
    "str", "int", "float", "list", "dict", "tuple", "range", "open",
    "isinstance", "super", "type", "log", "require", "join", "split",
    "strip", "append", "fetch", "then", "catch",
}

# A called name that resolves to more than this many definitions is too
# ambiguous to record — edges to all of them would inflate blast radius.
MAX_CALL_CANDIDATES = 3


def extract_call_graph(funcs_data: dict, files_text: dict[str, str]) -> dict:
    """Build function-to-function call edges across the codebase.

    Approach: regex-based identifier matching, with each function's body
    bounded by its loc_range. Noisy but fast — good enough for
    blast-radius grading, not for precise refactoring. Names defined in
    more than MAX_CALL_CANDIDATES places are skipped (counted as
    ambiguous) rather than fanned out to every definition.
    """
    name_lookup: dict[str, list[str]] = {}
    qname_to_loc: dict[str, tuple[str, int, int]] = {}

    for rel, file_data in funcs_data.get("files", {}).items():
        for fn in file_data.get("functions", []):
            qname = fn.get("qualified_name") or fn["name"]
            name_lookup.setdefault(fn["name"], []).append(qname)
            start, end = fn["loc_range"]
            qname_to_loc[qname] = (rel, start, end if end >= start else start + 100)

    print(f"cartographer stage 4: scanning {len(qname_to_loc)} function bodies for calls...", file=sys.stderr)

    edges: dict[str, dict[str, list]] = {q: {"calls": [], "called_by": []} for q in qname_to_loc}
    edge_count = 0
    ambiguous_skipped = 0

    for caller_qname, (rel, start, end) in qname_to_loc.items():
        text = files_text.get(rel, "")
        if not text:
            continue
        body = "\n".join(text.split("\n")[start - 1:end])
        body_clean = re.sub(r"//[^\n]*|#[^\n]*", "", body)
        for match in re.finditer(r"([a-z_][a-zA-Z0-9_]*)\s*\(", body_clean):
            called_name = match.group(1)
            if called_name in SKIP_NAMES:
                continue
            candidates = name_lookup.get(called_name, [])
            if len(candidates) > MAX_CALL_CANDIDATES:
                ambiguous_skipped += 1
                continue
            for callee_qname in candidates:
                if callee_qname == caller_qname:
                    continue  # skip pure self-recursion in edges
                if callee_qname not in [c["target"] for c in edges[caller_qname]["calls"]]:
                    edges[caller_qname]["calls"].append({"target": callee_qname})
                    edges[callee_qname]["called_by"].append({"caller": caller_qname})
                    edge_count += 1

    print(f"cartographer stage 4: extracted {edge_count} edges "
          f"({ambiguous_skipped} ambiguous call sites skipped)", file=sys.stderr)
    return edges


def prompt_user_for_call_graph(non_interactive: bool) -> bool:
    if non_interactive:
        return False
    print("", file=sys.stderr)
    print("cartographer: Stage 4 (call graph extraction) is optional.", file=sys.stderr)
    print("  - It produces richer audit-fix blast-radius grading.", file=sys.stderr)
    print("  - It costs an additional ~30-60 seconds at build time.", file=sys.stderr)
    print("  - It increases app-audit token cost by roughly 30-50% when consumed.", file=sys.stderr)
    print("", file=sys.stderr)
    try:
        ans = input("Run stage 4 now? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return ans in {"y", "yes"}


def cached_call_graph_is_fresh(per_file_state: dict) -> bool:
    """True if ≥90% of current files have UNCHANGED CONTENT versus the
    cache (content-hash comparison, not just file presence)."""
    if not CALL_GRAPH_CACHE.exists():
        return False
    try:
        cache = json.loads(CALL_GRAPH_CACHE.read_text())
    except Exception:
        return False
    cached_hashes: dict = cache.get("file_hashes", {})
    if not cached_hashes or not per_file_state:
        return False
    unchanged = sum(
        1 for rel, st in per_file_state.items()
        if cached_hashes.get(rel) == st["content_hash"]
    )
    return unchanged / len(per_file_state) >= 0.90


# ---------------------------------------------------------------------
# Tree walk — respects .gitignore via git ls-files when available
# ---------------------------------------------------------------------

def _interesting(fp: Path) -> bool:
    suffix = fp.suffix.lower()
    return (
        suffix in SOURCE_SUFFIXES or suffix in CONFIG_SUFFIXES
        or suffix in DOC_SUFFIXES or suffix in HTML_SUFFIXES
        or fp.name in ENTRY_POINT_NAMES
    )


def walk_tree() -> list[Path]:
    """List analyzable files. Uses `git ls-files` (tracked + untracked,
    .gitignore respected) when in a git repo; falls back to os.walk with
    SKIP_DIRS otherwise. SKIP_DIRS applies in both modes."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            out = []
            for line in result.stdout.splitlines():
                rel = line.strip()
                if not rel:
                    continue
                if any(part in SKIP_DIRS for part in Path(rel).parts):
                    continue
                fp = REPO_ROOT / rel
                if fp.is_file() and _interesting(fp):
                    out.append(fp)
            return sorted(set(out))
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    out = []
    for root, dirs, names in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in names:
            fp = Path(root) / n
            if _interesting(fp):
                out.append(fp)
    return sorted(set(out))


def guess_language(fp: Path) -> str | None:
    s = fp.suffix.lower()
    return {
        ".rs": "rust", ".py": "python", ".sh": "bash",
        ".js": "javascript", ".jsx": "javascript",
        ".mjs": "javascript", ".cjs": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".sql": "sql", ".toml": "toml",
        ".yaml": "yaml", ".yml": "yaml",
        ".json": "json", ".md": "markdown",
        ".mdx": "markdown", ".rst": "markdown",
        ".txt": "text", ".html": "html",
    }.get(s)


def first_meaningful_line(text: str) -> str:
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("//") or s.startswith("#") or s.startswith("--") or s.startswith("/*"):
            s = s.lstrip("/#-* ")
        if s:
            return s[:160]
    return ""


# ---------------------------------------------------------------------
# Warning detectors 1–7
# ---------------------------------------------------------------------

def detect_warnings(structure: dict, deps: dict, per_file_state: dict,
                    files_text: dict[str, str]) -> dict:
    warnings = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "detectors_run": [
            "duplicate_basenames", "suspicious_names", "backup_directories",
            "orphan_files", "near_duplicates", "stale_build_output",
            "canonical_designations",
        ],
        "summary": {},
        "duplicate_basenames": [],
        "suspicious_names": [],
        "backup_directories": [],
        "orphan_files": [],
        "near_duplicates": [],
        "stale_build_output": [],
        "canonical_designations": [],
        "codemap_drift": [],  # app-audit appends drift events here (Phase 0.5.6)
    }

    def non_test_importers(rel: str) -> list[str]:
        return [
            e["path"] for e in deps["graph"].get(rel, {}).get("imported_by", [])
            if not is_test_file(e["path"])
        ]

    # --- Detector 1: duplicate basenames (conventional names excluded) ---
    basename_to_paths: dict[str, list[str]] = {}
    for rel in structure["files"]:
        bn = Path(rel).name
        if bn in CONVENTIONAL_BASENAMES:
            continue
        basename_to_paths.setdefault(bn, []).append(rel)
    dup_clusters: list[list[str]] = []
    for bn, paths in sorted(basename_to_paths.items()):
        if len(paths) > 1:
            imported = [p for p in paths if non_test_importers(p)]
            severity = "high" if len(imported) > 1 else "medium"
            warnings["duplicate_basenames"].append({
                "basename": bn, "paths": sorted(paths),
                "imported_count": len(imported), "severity": severity,
                "concern": (
                    f"`{bn}` appears in {len(paths)} locations; "
                    f"{len(imported)} of them are imported by non-test code."
                ),
            })
            if any(structure["files"][p]["kind"] == "source" for p in paths):
                dup_clusters.append(sorted(paths))

    # --- Detector 2: suspicious names (migrations excluded from _v[N]) ---
    for rel in structure["files"]:
        path_parts = Path(rel).parts
        in_migrations = any(p.lower() in MIGRATION_DIRS for p in path_parts)
        name = Path(rel).name
        for pat, label in SUSPICIOUS_PATTERNS:
            if in_migrations and label == "*_v[N].*":
                continue  # migrations/_v[N] is sequenced, not stale
            if pat.match(name):
                n_importers = len(non_test_importers(rel))
                imported_note = (
                    f"Imported by {n_importers} non-test file(s)." if n_importers
                    else "Not imported by any non-test file."
                )
                warnings["suspicious_names"].append({
                    "path": rel, "pattern": label,
                    "severity": "medium",
                    "concern": f"Filename `{name}` matches pattern `{label}`. {imported_note}",
                    "imported_by_count": n_importers,
                })
                break

    # --- Detector 3: backup directories ---
    all_dirs: dict[str, int] = {}
    for rel in structure["files"]:
        d = posixpath.dirname(rel)
        while d:
            all_dirs[d] = all_dirs.get(d, 0) + 1
            d = posixpath.dirname(d)
    top_level = {posixpath.normpath(d).split("/")[0] for d in all_dirs}
    for d in sorted(all_dirs):
        base = posixpath.basename(d)
        matched = None
        for pat, label in BACKUP_DIR_PATTERNS:
            if pat.match(base):
                matched = label
                break
        if not matched and base.startswith("src_") and "src" in top_level:
            matched = "src_* (sibling of src/)"
        if matched:
            externally_imported = any(
                rel.startswith(d + "/") and any(not imp.startswith(d + "/") for imp in non_test_importers(rel))
                for rel in structure["files"]
            )
            warnings["backup_directories"].append({
                "path": d, "pattern": matched,
                "file_count": all_dirs[d],
                "severity": "high" if externally_imported else "medium",
                "concern": (
                    f"Directory `{d}` matches backup/archive pattern `{matched}` "
                    f"({all_dirs[d]} files)."
                    + (" Files inside are imported from outside the directory." if externally_imported else "")
                ),
            })

    # --- Detector 4: orphan files ---
    # Tests, migrations, and entry points are legitimately un-imported;
    # only flag languages where import extraction actually ran. Files inside
    # an already-flagged backup directory are covered by detector 3.
    backup_dir_prefixes = tuple(w["path"] + "/" for w in warnings["backup_directories"])
    importable_langs = {"rust", "python", "typescript", "javascript"}
    for rel, struct in structure["files"].items():
        if struct["kind"] != "source" or struct["entry_point"] or struct["test_file"]:
            continue
        if struct["language"] not in importable_langs:
            continue
        if "migration" in struct.get("tags", []):
            continue
        if backup_dir_prefixes and rel.startswith(backup_dir_prefixes):
            continue
        if not deps["graph"].get(rel, {}).get("imported_by", []):
            warnings["orphan_files"].append({
                "path": rel, "severity": "medium",
                "concern": (
                    "Source file has no `imported_by` entries; may be dead code. "
                    "Import resolution is best-effort static — check for dynamic "
                    "loading or build-config entry points before deleting."
                ),
                "is_entry_point": False,
                "suggested_action": "Verify the file is reachable; remove if dead.",
            })

    # --- Detector 5: near-duplicate content ---
    def line_set(rel: str) -> set:
        return {ln.strip() for ln in files_text.get(rel, "").split("\n") if ln.strip()}

    near_dup_clusters: list[list[str]] = []
    source_rels = [r for r, s in structure["files"].items()
                   if s["kind"] == "source" and 0 < s["loc"] <= 4000]
    by_dir: dict[str, list[str]] = {}
    for rel in source_rels:
        by_dir.setdefault(posixpath.dirname(rel), []).append(rel)
    candidate_pairs: set = set()
    for rels in by_dir.values():
        for i in range(len(rels)):
            for j in range(i + 1, len(rels)):
                a, b = rels[i], rels[j]
                if Path(a).suffix == Path(b).suffix:
                    candidate_pairs.add((a, b))
    for cluster in dup_clusters:  # duplicate basenames across dirs
        for i in range(len(cluster)):
            for j in range(i + 1, len(cluster)):
                candidate_pairs.add(tuple(sorted((cluster[i], cluster[j]))))
    compared = 0
    for a, b in sorted(candidate_pairs):
        if compared >= 5000:
            warnings.setdefault("notes", []).append(
                "near-duplicate comparison capped at 5000 pairs; coverage incomplete")
            break
        loc_a, loc_b = structure["files"][a]["loc"], structure["files"][b]["loc"]
        if loc_a == 0 or loc_b == 0 or min(loc_a, loc_b) / max(loc_a, loc_b) < 0.7:
            continue
        sa, sb = line_set(a), line_set(b)
        if not sa or not sb:
            continue
        compared += 1
        jaccard = len(sa & sb) / len(sa | sb)
        if jaccard >= 0.85:
            warnings["near_duplicates"].append({
                "paths": [a, b], "similarity": round(jaccard, 3),
                "severity": "high",
                "concern": f"`{a}` and `{b}` are ~{round(jaccard * 100)}% identical — likely an unfinished refactor.",
            })
            near_dup_clusters.append([a, b])

    # --- Detector 6: stale build output (older than latest source change) ---
    newest_src_mtime = 0.0
    for rel in structure["files"]:
        try:
            newest_src_mtime = max(newest_src_mtime, (REPO_ROOT / rel).stat().st_mtime)
        except OSError:
            continue
    for out_dir in BUILD_OUTPUT_DIRS:
        out_path = REPO_ROOT / out_dir
        if not out_path.is_dir():
            continue
        newest_out, file_count = 0.0, 0
        for root, _dirs, names in os.walk(out_path):
            for n in names:
                file_count += 1
                if file_count > 2000:
                    break
                try:
                    newest_out = max(newest_out, (Path(root) / n).stat().st_mtime)
                except OSError:
                    continue
            if file_count > 2000:
                break
        if file_count and newest_out and newest_out < newest_src_mtime - 60:
            warnings["stale_build_output"].append({
                "path": out_dir, "severity": "medium",
                "concern": (
                    f"Build output in `{out_dir}/` is older than the latest source "
                    "change — a launched app may be serving stale code. Rebuild."
                ),
            })

    # --- Detector 7: canonical designation for duplicate/near-dup clusters ---
    seen_clusters: set = set()
    near_dup_keys = {tuple(sorted(c)) for c in near_dup_clusters}
    for cluster in dup_clusters + near_dup_clusters:
        key = tuple(sorted(cluster))
        if key in seen_clusters or len(cluster) < 2:
            continue
        seen_clusters.add(key)
        designation = designate_canonical(
            list(key), structure, per_file_state, non_test_importers,
            from_near_dup=key in near_dup_keys,
        )
        if designation:
            warnings["canonical_designations"].append(designation)

    warnings["summary"] = {k: len(warnings[k]) for k in (
        "duplicate_basenames", "suspicious_names", "backup_directories",
        "orphan_files", "near_duplicates", "stale_build_output",
        "canonical_designations",
    )}
    return warnings


def designate_canonical(cluster: list[str], structure: dict, per_file_state: dict,
                        non_test_importers, *, from_near_dup: bool = False) -> dict | None:
    """Pick one canonical file per duplicate cluster (detector 7).

    Priority: import-graph reachability → most recent commit → name/size
    score → alphabetical (noted as arbitrary). Imports split between
    candidates, or unresolvable ties, are designated `ambiguous`.

    Note: "most recent commit" uses the latest commit touching the file —
    this script does not filter out cosmetic/format-only commits (the
    direct path can be smarter about that).
    """
    def suspicious_score(rel: str) -> int:
        name = Path(rel).name
        return sum(1 for pat, _ in SUSPICIOUS_PATTERNS if pat.match(name))

    with_importers = [p for p in cluster if non_test_importers(p)]
    canonical, reason = None, None

    if len(with_importers) == 1:
        canonical, reason = with_importers[0], "import_graph_reachability"
    elif len(with_importers) > 1:
        # Imports split between candidates — the genuinely dangerous case.
        canonical = max(with_importers, key=lambda p: per_file_state.get(p, {}).get("last_commit_ts", 0))
        reason = "ambiguous"
    else:
        by_ts = sorted(cluster, key=lambda p: per_file_state.get(p, {}).get("last_commit_ts", 0), reverse=True)
        ts0 = per_file_state.get(by_ts[0], {}).get("last_commit_ts", 0)
        ts1 = per_file_state.get(by_ts[1], {}).get("last_commit_ts", 0)
        if ts0 and ts0 != ts1:
            canonical, reason = by_ts[0], "most_recent_commit"
        else:
            scored = sorted(
                cluster,
                key=lambda p: (suspicious_score(p), -structure["files"][p]["loc"], p),
            )
            best, runner = scored[0], scored[1]
            if (suspicious_score(best), structure["files"][best]["loc"]) != \
               (suspicious_score(runner), structure["files"][runner]["loc"]):
                canonical, reason = best, "loc_and_naming"
            else:
                canonical, reason = scored[0], "alphabetical_tiebreak"

    stale = [p for p in cluster if p != canonical]
    concern_bits = []
    for p in cluster:
        n = len(non_test_importers(p))
        concern_bits.append(f"`{p}` ({n} importer{'s' if n != 1 else ''})")
    severity = "high" if from_near_dup or reason in ("ambiguous", "alphabetical_tiebreak") or \
        any(structure["files"][p].get("kind") == "source" and non_test_importers(p) for p in stale) \
        else "medium"
    note = " Tiebreak was arbitrary — verify manually." if reason == "alphabetical_tiebreak" else ""
    return {
        "cluster": cluster,
        "canonical": canonical,
        "stale_candidates": stale,
        "designation_reason": reason,
        "concern": "Duplicate cluster: " + ", ".join(concern_bits) + "." + note,
        "severity": severity,
        "suggested_action": f"Remove or archive {', '.join(stale)} if confirmed dead.",
    }


# ---------------------------------------------------------------------
# spec-config.yml loader (top-level keys, lists, and one nested mapping)
# ---------------------------------------------------------------------

def load_spec_config() -> dict:
    cfg_path = CODEMAP_DIR / "spec-config.yml"
    if not cfg_path.exists():
        return {}
    cfg: dict = {}
    current_key = None
    current_mode = None  # "list" | "dict"
    for line in cfg_path.read_text().split("\n"):
        line = line.split("#", 1)[0].rstrip()
        if not line:
            continue
        if line.startswith("  - ") and current_key and current_mode in (None, "list"):
            if not isinstance(cfg.get(current_key), list):
                cfg[current_key] = []
            cfg[current_key].append(line[4:].strip())
            current_mode = "list"
        elif line.startswith("  ") and ":" in line and current_key and current_mode in (None, "dict"):
            k, _, v = line.strip().partition(":")
            if not isinstance(cfg.get(current_key), dict):
                cfg[current_key] = {}
            cfg[current_key][k.strip()] = v.strip().strip("\"'")
            current_mode = "dict"
        elif ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip().strip("\"'")
            if not value:
                cfg[key] = None  # container type decided by first child line
                current_key, current_mode = key, None
            else:
                cfg[key] = value
                current_key, current_mode = None, None
    # Keys that declared a block but got no children → empty list
    for k, v in list(cfg.items()):
        if v is None:
            cfg[k] = []
    return cfg


def spec_config_hash() -> str:
    cfg_path = CODEMAP_DIR / "spec-config.yml"
    if not cfg_path.exists():
        return ""
    return hashlib.sha256(cfg_path.read_bytes()).hexdigest()[:16]


# ---------------------------------------------------------------------
# Prior-state loading for incremental refresh
# ---------------------------------------------------------------------

def load_prior() -> dict | None:
    """Load the previous codemap for incremental reuse. Returns None when
    a full rebuild is needed (missing, corrupt, or version-mismatched)."""
    try:
        state = json.loads((CODEMAP_DIR / "state.json").read_text())
        if state.get("schema_version") != STATE_SCHEMA_VERSION:
            return None
        if state.get("cartographer_version") != CARTOGRAPHER_VERSION:
            print("cartographer: version changed — full rebuild", file=sys.stderr)
            return None
        return {
            "state": state,
            "structure": json.loads((CODEMAP_DIR / "structure.json").read_text()),
            "deps": json.loads((CODEMAP_DIR / "dependencies.json").read_text()),
            "funcs": json.loads((CODEMAP_DIR / "functions.json").read_text()),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Cartographer build script")
    parser.add_argument("--with-call-graph", action="store_true",
                        help="Run stage 4 (call graph extraction)")
    parser.add_argument("--no-call-graph", action="store_true",
                        help="Skip stage 4 even if cache exists")
    parser.add_argument("--rebuild-call-graph", action="store_true",
                        help="Force-rebuild stage 4 cache")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Never prompt; treat stage 4 as off unless --with-call-graph")
    parser.add_argument("--full", action="store_true",
                        help="Ignore prior state; full rebuild")
    args = parser.parse_args()

    spec_cfg = load_spec_config()
    cfg_hash = spec_config_hash()

    prior = None if args.full else load_prior()
    prior_state_files: dict = prior["state"].get("per_file_state", {}) if prior else {}
    spec_cfg_changed = bool(prior) and prior["state"].get("spec_config_hash", "") != cfg_hash
    if spec_cfg_changed:
        print("cartographer: spec-config.yml changed — re-analyzing docs and spec_refs", file=sys.stderr)

    files = walk_tree()
    print(f"cartographer: walked {len(files)} files", file=sys.stderr)

    structure = {"schema_version": 1, "generated_at": utc_now_iso(),
                 "root": str(REPO_ROOT), "languages_detected": set(),
                 "files_count": 0, "directories": [], "files": {}}
    deps = {"schema_version": 1, "generated_at": utc_now_iso(), "graph": {}}
    funcs = {"schema_version": 1, "generated_at": utc_now_iso(),
             "files": {}, "build_metadata": {
                 "build_method": "py-script-richer",
                 "stages_run": ["1_tags", "2_spec_refs", "3_qualified_names"],
             }}
    per_file_state: dict = {}
    files_text: dict[str, str] = {}
    reused = analyzed = 0

    # Pick the canonical spec if config doesn't name one (announced, not silent).
    if not spec_cfg.get("canonical_spec"):
        best, best_sections = None, 2
        for fp in files:
            if fp.suffix.lower() not in (".md", ".mdx"):
                continue
            rel = fp.relative_to(REPO_ROOT).as_posix()
            if not SPEC_DOC_NAME_RE.search(fp.name):
                continue
            try:
                n = section_count_in(fp.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, OSError):
                continue
            if n > best_sections:
                best, best_sections = rel, n
        if best:
            spec_cfg["canonical_spec"] = best
            print(f"cartographer: no spec-config.yml canonical_spec — picked `{best}` "
                  f"by filename + section density. Add .codemap/spec-config.yml to override.",
                  file=sys.stderr)

    for fp in files:
        rel = fp.relative_to(REPO_ROOT).as_posix()
        try:
            text = fp.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        h = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        language = guess_language(fp)
        files_text[rel] = text

        # ---- Incremental reuse: unchanged content → copy prior analysis ----
        prior_entry = prior_state_files.get(rel) if prior else None
        doc_needs_refresh = spec_cfg_changed and language == "markdown"
        refs_need_refresh = spec_cfg_changed  # tag_spec_map may have changed
        if (prior_entry and prior_entry.get("content_hash") == h
                and rel in prior["structure"]["files"] and not doc_needs_refresh
                and not refs_need_refresh):
            structure["files"][rel] = prior["structure"]["files"][rel]
            if structure["files"][rel].get("language") not in (None, "unknown"):
                structure["languages_detected"].add(structure["files"][rel]["language"])
            deps["graph"][rel] = {
                "imports_from": prior["deps"]["graph"].get(rel, {}).get("imports_from", []),
                "imported_by": [],  # recomputed below
            }
            if rel in prior["funcs"].get("files", {}):
                fdata = prior["funcs"]["files"][rel]
                for fn in fdata.get("functions", []):
                    fn["calls"], fn["called_by"] = [], []  # stage 4 repopulates
                funcs["files"][rel] = fdata
            per_file_state[rel] = prior_entry
            reused += 1
            continue

        # ---- Fresh analysis ----
        analyzed += 1
        size = fp.stat().st_size
        loc = len(text.split("\n"))
        if language:
            structure["languages_detected"].add(language)

        purpose = ""
        tags: list[str] = []
        kind = "source"
        doc_class = None
        section_count = 0
        is_canonical_spec = False
        imports: list[dict] = []
        functions: list[dict] = []
        file_spec_refs: list[dict] = []
        last_commit, last_commit_ts = "", 0

        if language == "markdown":
            kind = "documentation"
            doc_class = classify_doc(rel, text, spec_cfg)
            section_count = section_count_in(text)
            is_canonical_spec = (rel == spec_cfg.get("canonical_spec"))
            tags = ["documentation", doc_class]
            purpose = first_meaningful_line(text)
        elif language in {"rust", "python", "typescript", "javascript", "sql", "bash"}:
            tags = infer_tags(rel, language)
            file_spec_refs = infer_file_spec_refs(rel, text, tags, spec_cfg)
            purpose = first_meaningful_line(text)
            last_commit, last_commit_ts = file_last_commit(rel)  # Stage 3
            qualified_prefix = compute_qualified_prefix(rel, language)
            fn_kwargs = dict(
                qualified_prefix=qualified_prefix,
                file_tags=tags,
                file_spec_refs=file_spec_refs,
                file_last_commit_hash=last_commit,
            )
            if language == "rust":
                imports = extract_rust_imports(text)
                functions = extract_rust_functions(text, **fn_kwargs)
            elif language == "python":
                imports = extract_python_imports(text)
                functions = extract_python_functions(text, **fn_kwargs)
            elif language in {"typescript", "javascript"}:
                imports = extract_ts_imports(text)
                functions = extract_ts_functions(text, **fn_kwargs)
            if functions:
                lines = text.split("\n")
                finalize_loc_ranges(functions, loc)
                attach_nearby_spec_refs(functions, lines)
        elif language in {"toml", "yaml", "json"}:
            kind = "config"
            tags = ["config"]
        else:
            kind = "other"

        entry_point = (
            fp.name in ENTRY_POINT_NAMES
            or text.startswith("#!")
            or posixpath.dirname(rel).split("/")[0] in ("bin", "scripts", "tools")
        )

        struct_entry = {
            "kind": kind, "language": language or "unknown",
            "loc": loc, "size_bytes": size,
            "purpose": purpose, "tags": tags,
            "spec_refs": file_spec_refs,
            "entry_point": entry_point,
            "test_file": is_test_file(rel),
        }
        if doc_class:
            struct_entry["doc_class"] = doc_class
            struct_entry["section_count"] = section_count
            if is_canonical_spec:
                struct_entry["is_canonical_spec"] = True
        structure["files"][rel] = struct_entry

        deps["graph"][rel] = {"imports_from": imports, "imported_by": []}
        if functions:
            funcs["files"][rel] = {"functions": functions}

        per_file_state[rel] = {
            "content_hash": h,
            "last_commit": last_commit,
            "last_commit_ts": last_commit_ts,
        }

    structure["files_count"] = len(structure["files"])
    structure["languages_detected"] = sorted(structure["languages_detected"])
    deleted = len(prior_state_files) - sum(1 for r in prior_state_files if r in per_file_state) if prior else 0
    print(f"cartographer: {analyzed} analyzed, {reused} reused (unchanged), {deleted} deleted",
          file=sys.stderr)

    # 3. Cross-references — resolve imports to files, populate imported_by.
    all_files_set = set(structure["files"].keys())
    rust_index = build_rust_module_index(
        [r for r, s in structure["files"].items() if s["language"] == "rust"])
    for src, info in deps["graph"].items():
        lang = structure["files"][src]["language"]
        for imp in info["imports_from"]:
            resolved = None
            if lang == "rust":
                resolved = resolve_rust_import(imp, src, rust_index, all_files_set)
            elif lang == "python":
                resolved = resolve_python_import(imp, src, all_files_set)
            elif lang in {"typescript", "javascript"}:
                resolved = resolve_ts_import(imp, src, all_files_set)
            imp["resolved"] = resolved
            if resolved and resolved in deps["graph"]:
                deps["graph"][resolved]["imported_by"].append({
                    "path": src, "symbols": imp.get("symbols", []),
                    "kind": imp.get("kind", "import"),
                })

    # 4. Stage 4 — Call graph (opt-in)
    run_stage_4 = False
    cache_valid = cached_call_graph_is_fresh(per_file_state) and not args.rebuild_call_graph

    if args.no_call_graph:
        run_stage_4 = False
    elif args.with_call_graph or args.rebuild_call_graph:
        run_stage_4 = True
    elif cache_valid:
        print("cartographer: reusing cached call graph (≥90% content unchanged)", file=sys.stderr)
        try:
            cache = json.loads(CALL_GRAPH_CACHE.read_text())
            cached_edges = cache.get("edges", {})
            for rel, file_data in funcs["files"].items():
                for fn in file_data["functions"]:
                    qname = fn.get("qualified_name")
                    if qname in cached_edges:
                        fn["calls"] = cached_edges[qname].get("calls", [])
                        fn["called_by"] = cached_edges[qname].get("called_by", [])
            funcs["build_metadata"]["stages_run"].append("4_call_graph_cached")
        except Exception as e:
            print(f"cartographer: cache load failed ({e}), running fresh", file=sys.stderr)
            run_stage_4 = prompt_user_for_call_graph(args.non_interactive)
    else:
        run_stage_4 = prompt_user_for_call_graph(args.non_interactive)

    if run_stage_4:
        edges = extract_call_graph(funcs, files_text)
        for rel, file_data in funcs["files"].items():
            for fn in file_data["functions"]:
                qname = fn.get("qualified_name")
                if qname in edges:
                    fn["calls"] = edges[qname].get("calls", [])
                    fn["called_by"] = edges[qname].get("called_by", [])
        funcs["build_metadata"]["stages_run"].append("4_call_graph")
        CALL_GRAPH_CACHE.write_text(json.dumps({
            "schema_version": 2,
            "generated_at": utc_now_iso(),
            "file_hashes": {r: st["content_hash"] for r, st in per_file_state.items()},
            "edges": edges,
        }, indent=2))
        print(f"cartographer: stage 4 cache written to {CALL_GRAPH_CACHE.name}", file=sys.stderr)

    # 5. Warning detectors (all seven)
    warnings = detect_warnings(structure, deps, per_file_state, files_text)
    # Preserve drift events app-audit logged against the previous codemap state.
    if prior:
        try:
            prior_warnings = json.loads((CODEMAP_DIR / "warnings.json").read_text())
            warnings["codemap_drift"] = [
                d for d in prior_warnings.get("codemap_drift", [])
                if per_file_state.get(d.get("path", ""), {}).get("content_hash") ==
                   prior_state_files.get(d.get("path", ""), {}).get("content_hash")
            ]
        except Exception:
            pass

    # 6. Write everything
    head = git_head() + ("-dirty" if git_dirty() else "")
    prior_created = prior["state"].get("created_at") if prior else None
    prior_full_build_at = prior["state"].get("last_full_build_at") if prior else None
    prior_full_build_commit = prior["state"].get("last_full_build_commit") if prior else None
    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "cartographer_version": CARTOGRAPHER_VERSION,
        "created_at": prior_created or utc_now_iso(),
        "last_full_build_at": prior_full_build_at or utc_now_iso(),
        "last_full_build_commit": prior_full_build_commit or head,
        "last_refresh_at": utc_now_iso(),
        "last_refresh_commit": head,
        "spec_config_hash": cfg_hash,
        "build_metadata": {
            "files_processed": len(per_file_state),
            "files_analyzed": analyzed,
            "files_reused": reused,
            "languages_detected": structure["languages_detected"],
            "build_method": "py-script-richer",
            "stages_run": funcs["build_metadata"]["stages_run"],
        },
        # The honesty contract: consumers check this before trusting a field.
        "capabilities": {
            "incremental_refresh": True,
            "respects_gitignore": True,
            "function_extraction_languages": ["rust", "python", "typescript", "javascript"],
            "import_extraction_languages": ["rust", "python", "typescript", "javascript"],
            "import_resolution": "best-effort-static",
            "detectors_run": warnings["detectors_run"],
            "call_graph": "regex-best-effort (stage 4, opt-in)",
        },
        "configured_entry_points": sorted(ENTRY_POINT_NAMES),
        "per_file_state": per_file_state,
    }

    CODEMAP_DIR.mkdir(exist_ok=True)
    write_json(CODEMAP_DIR / "structure.json", structure)
    write_json(CODEMAP_DIR / "dependencies.json", deps)
    write_json(CODEMAP_DIR / "functions.json", funcs)
    write_json(CODEMAP_DIR / "warnings.json", warnings)
    write_json(CODEMAP_DIR / "state.json", state)

    high = sum(
        1 for k in warnings["summary"]
        for w in warnings[k] if isinstance(w, dict) and w.get("severity") == "high"
    )
    print(
        f"cartographer: complete. files={len(per_file_state)} "
        f"(analyzed={analyzed} reused={reused}) "
        f"stages={','.join(funcs['build_metadata']['stages_run'])} "
        f"warnings={sum(warnings['summary'].values())} (high={high})",
        file=sys.stderr,
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False, default=str))


if __name__ == "__main__":
    main()
