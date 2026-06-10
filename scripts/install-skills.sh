#!/usr/bin/env bash
# Install the five DevLoop skills into Claude Code's skill directory so the loop
# driver (and interactive Claude Code sessions) can load them.
#
# selran-devloop/skills/ is the source of truth. This copies them to
# ~/.claude/skills/ (the location Claude Code reads at runtime).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../skills" && pwd)"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
mkdir -p "$DEST"

for skill in cartographer pre-commit-verification spec-bootstrap app-audit audit-fix; do
  if [[ ! -d "$SRC/$skill" ]]; then
    echo "  skip (not found in repo): $skill" >&2
    continue
  fi
  rsync -a --delete --exclude='.DS_Store' "$SRC/$skill/" "$DEST/$skill/"
  ver="$(grep '^version:' "$DEST/$skill/SKILL.md" 2>/dev/null || echo 'version: (none)')"
  echo "installed: $skill ($ver) -> $DEST/$skill"
done

echo "done."
