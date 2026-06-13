#!/usr/bin/env bash
# Greenloop PostToolUse — opt-in auto-format of the file just edited.
#
# OFF by default: this is a global plugin hook, so it would otherwise reformat
# every file the user edits in any repo — too intrusive, and whole-file
# reformats muddy audit-fix's minimal per-fix diffs. Enable deliberately with
#   export GREENLOOP_AUTOFORMAT=1
# Always exits 0; never fails the tool call.
set -uo pipefail

[ "${GREENLOOP_AUTOFORMAT:-}" = "1" ] || exit 0

input=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
[ -z "$file" ] && exit 0
[ -f "$file" ] || exit 0

have() { command -v "$1" >/dev/null 2>&1; }

case "$file" in
  *.rs)
    have rustfmt && rustfmt "$file" >/dev/null 2>&1
    ;;
  *.py)
    if have ruff; then ruff format "$file" >/dev/null 2>&1
    elif have black; then black -q "$file" >/dev/null 2>&1; fi
    ;;
  *.go)
    have gofmt && gofmt -w "$file" >/dev/null 2>&1
    ;;
  *.js | *.jsx | *.ts | *.tsx | *.json | *.css | *.scss | *.md | *.html | *.yaml | *.yml)
    have prettier && prettier --write "$file" >/dev/null 2>&1
    ;;
esac
exit 0
