#!/usr/bin/env bash
# Greenloop PreToolUse guard — the enforcement layer.
#
# During an active app-audit *review* window, physically block edits to source
# code so the auditor cannot silently "fix while it reviews" (the eight-eyes /
# mumei discipline: a reviewer that can edit anchors on its own narrative and
# stops finding things). The window is delimited by a marker file the audit
# skill writes at Phase 3 and removes at Phase 5 — so this guard is INERT for
# all normal work, including audit-fix, which runs after the window closes.
#
# Fail-open on any uncertainty. A code-review plugin must never wedge a user's
# editing because jq is missing or a path looks odd.
set -uo pipefail

# Hard escape hatch.
[ "${GREENLOOP_BYPASS:-}" = "1" ] && exit 0

input=$(cat)
command -v jq >/dev/null 2>&1 || exit 0   # no jq → fail open

cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
[ -z "$cwd" ] && exit 0

# Walk up from cwd looking for an active-audit marker.
root=""
dir="$cwd"
while [ -n "$dir" ] && [ "$dir" != "/" ]; do
  if [ -f "$dir/.audit/.audit-active" ]; then root="$dir"; break; fi
  dir=$(dirname "$dir")
done
[ -z "$root" ] && exit 0   # no audit in progress → allow

marker="$root/.audit/.audit-active"

# Stale-marker safety: a marker older than 6h is from a crashed/abandoned
# session. Clean it and allow — never block forever on a leftover file.
if [ -n "$(find "$marker" -mmin +360 2>/dev/null)" ]; then
  rm -f "$marker" "$root/.audit/.guard-attempts" 2>/dev/null
  exit 0
fi

# The audit writes its own state — always allow those paths.
case "$file" in
  "$root"/.audit/* | "$root"/AUDIT_LOG.md | */AUDIT_LOG.md) exit 0 ;;
  "") exit 0 ;;   # no file target (shouldn't happen for Edit/Write) → allow
esac

# Block, with nudge escalation so a determined override gets the bypass hint.
attempts_file="$root/.audit/.guard-attempts"
n=$(( $(cat "$attempts_file" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$attempts_file" 2>/dev/null || true

extra=""
[ "$n" -ge 3 ] && extra=" (attempt $n — if you truly must edit during the audit, set GREENLOOP_BYPASS=1; otherwise finish the audit and let audit-fix apply changes.)"

reason="Greenloop: an app-audit review is in progress, so the auditor is read-only — record this as a finding in AUDIT_LOG.md instead of editing. Remediation happens in audit-fix after the audit closes, where every fix is blast-radius-ordered and individually verified.${extra}"

jq -n --arg r "$reason" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: $r
  }
}'
exit 0
