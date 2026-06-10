#!/usr/bin/env bash
# Install the five DevLoop skills into Codex's skill directory.
#
# selran-devloop/skills/ is the source of truth. This copies them to
# ~/.codex/skills/ so Codex can load them after restart.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../skills" && pwd)"
DEST="${CODEX_SKILLS_DIR:-$HOME/.codex/skills}"
BACKUP_ROOT="${CODEX_SKILL_BACKUP_DIR:-$HOME/.codex/skill-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$DEST" "$BACKUP_ROOT"

for skill in cartographer pre-commit-verification spec-bootstrap app-audit audit-fix; do
  if [[ ! -d "$SRC/$skill" ]]; then
    echo "skip (not found in repo): $skill" >&2
    continue
  fi

  if [[ -d "$DEST/$skill" ]]; then
    cp -R "$DEST/$skill" "$BACKUP_ROOT/$skill-$STAMP"
    echo "backed up: $DEST/$skill -> $BACKUP_ROOT/$skill-$STAMP"
  fi

  rm -rf "$DEST/$skill"
  cp -R "$SRC/$skill" "$DEST/$skill"
  ver="$(grep '^version:' "$DEST/$skill/SKILL.md" 2>/dev/null || echo 'version: (none)')"
  echo "installed: $skill ($ver) -> $DEST/$skill"
done

echo "done. Restart Codex to pick up new skills automatically."
