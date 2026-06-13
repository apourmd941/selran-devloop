#!/usr/bin/env bash
# Export the five Greenloop skills for agent CLIs other than Claude Code.
#
# Two modes:
#   --agents-md [outfile]   Bundle all five SKILL.md files into one
#                           AGENTS.md-style instruction file (default:
#                           ./GREENLOOP-AGENTS.md) for hosts that read
#                           AGENTS.md / rules files (OpenCode, Cursor, ...).
#                           References (references/*) are NOT inlined — the
#                           bundle points at this repo's skills/ tree.
#   --copy <dir>            Copy the five skill directories (SKILL.md +
#                           references) into <dir>, for hosts with a
#                           skills-directory convention. (For Codex
#                           specifically, prefer install-codex-skills.sh,
#                           which also backs up existing copies.)
#
# The skills are plain-markdown methodology — portable to any agent host.
# The enforcement layers (hooks/, agents/) are Claude Code plugin features
# and are intentionally not exported; see docs/ADAPTERS.md.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../skills" && pwd)"
SKILLS=(cartographer pre-commit-verification spec-bootstrap app-audit audit-fix)

usage() { sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

mode="${1:-}"
case "$mode" in
  --agents-md)
    out="${2:-GREENLOOP-AGENTS.md}"
    {
      echo "# Greenloop — the loop that runs until green (skill bundle)"
      echo
      echo "Methodology skills by Selran (Aidin Eslampour) — bundled for"
      echo "AGENTS.md-style hosts. Source of truth:"
      echo "https://github.com/apourmd941/selran-devloop (skills/)."
      echo "Reference files cited as references/<name> live in that repo"
      echo "under skills/<skill>/references/."
      echo
      echo "Skills in this bundle:"
      for s in "${SKILLS[@]}"; do
        v="$(grep -m1 '^version:' "$SRC/$s/SKILL.md" | cut -d' ' -f2 || true)"
        echo "- $s ${v:+(v$v)}"
      done
      for s in "${SKILLS[@]}"; do
        echo
        echo "---"
        echo
        # strip YAML frontmatter (first --- ... --- block); keep the body
        awk 'BEGIN{fm=0} NR==1 && /^---$/{fm=1; next} fm==1 && /^---$/{fm=2; next} fm!=1{print}' \
          "$SRC/$s/SKILL.md"
      done
    } > "$out"
    echo "wrote: $out ($(wc -l < "$out" | tr -d ' ') lines, ${#SKILLS[@]} skills)"
    echo "note: references/* are cited, not inlined — keep the repo cloned for deep recipes."
    ;;
  --copy)
    dest="${2:?usage: $0 --copy <skills-dir>}"
    mkdir -p "$dest"
    for s in "${SKILLS[@]}"; do
      rm -rf "${dest:?}/$s"
      cp -R "$SRC/$s" "$dest/$s"
      v="$(grep -m1 '^version:' "$dest/$s/SKILL.md" || echo 'version: (none)')"
      echo "installed: $s ($v) -> $dest/$s"
    done
    echo "done. Restart the host agent so it picks up the skills."
    ;;
  -h|--help) usage ;;
  *) usage 1 ;;
esac
