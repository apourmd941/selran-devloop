#!/usr/bin/env bash
# Greenloop SessionStart — surface greenloop state at session start so the user
# knows before they ask: is the codemap stale? are there open findings? It also
# cleans a stale audit marker left by a crashed session. Silent unless there's
# something to say; always exits 0.
set -uo pipefail

input=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
[ -z "$cwd" ] && exit 0
cd "$cwd" 2>/dev/null || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# Clean a stale active-audit marker (>6h) from a crashed session so the
# read-only guard doesn't wedge this session.
if [ -f .audit/.audit-active ] && [ -n "$(find .audit/.audit-active -mmin +360 2>/dev/null)" ]; then
  rm -f .audit/.audit-active .audit/.guard-attempts 2>/dev/null || true
fi

msgs=""

# Stale codemap?
if [ -f .codemap/state.json ]; then
  last=$(jq -r '.last_refresh_commit // .build_metadata.commit // empty' .codemap/state.json 2>/dev/null)
  head=$(git rev-parse HEAD 2>/dev/null || true)
  if [ -n "$last" ] && [ -n "$head" ] && [ "$last" != "$head" ]; then
    behind=$(git rev-list --count "$last".."$head" 2>/dev/null || echo "")
    if [ -n "$behind" ] && [ "$behind" != "0" ]; then
      msgs="${msgs}Greenloop: the codemap (.codemap) is ${behind} commit(s) behind HEAD — refresh cartographer before auditing for accurate retrieval. "
    fi
  fi
fi

# Open findings waiting?
if [ -f AUDIT_LOG.md ]; then
  open=$(grep -c -- '— open' AUDIT_LOG.md 2>/dev/null || echo 0)
  if [ "${open:-0}" -gt 0 ] 2>/dev/null; then
    msgs="${msgs}Greenloop: AUDIT_LOG.md has ${open} open finding(s) — invoke audit-fix to work through them. "
  fi
fi

[ -z "$msgs" ] && exit 0

jq -n --arg c "$msgs" '{
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    additionalContext: $c
  }
}'
exit 0
