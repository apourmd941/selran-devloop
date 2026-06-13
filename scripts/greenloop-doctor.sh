#!/usr/bin/env bash
# greenloop-doctor — report which deterministic-detector tiers are live.
#
# Greenloop's highest-confidence findings are grounded in real analyzers
# (Step 3.0). When a detector is missing, that tier silently degrades to
# judgement-only — lower confidence, more false positives. This probe makes the
# degradation VISIBLE: it reports which tiers are live, what's missing, and the
# exact command to install each one. app-audit runs it at the start of a round
# and records the result; humans run it before a release.
#
# Usage:
#   greenloop-doctor.sh            # human-readable readiness table for the cwd repo
#   greenloop-doctor.sh --json     # machine-readable (app-audit / status.json consume this)
#   greenloop-doctor.sh --install  # install the missing UNIVERSAL detectors (asks first)
#   greenloop-doctor.sh -h         # help
#
# Exit code: 0 if all UNIVERSAL tiers (sast, deps, secrets) are live, else 1.
set -uo pipefail

JSON=0; INSTALL=0
for a in "$@"; do
  case "$a" in
    --json) JSON=1 ;;
    --install) INSTALL=1 ;;
    -h|--help) sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown arg: $a" >&2; exit 2 ;;
  esac
done

have() { command -v "$1" >/dev/null 2>&1; }
ver()  { "$1" --version 2>/dev/null | head -1 | tr -d '\n' | cut -c1-40; }

# Detect the repo's stack so we only *require* the type-checkers that apply.
STACK=""
[ -f package.json ] && STACK="$STACK node"
{ [ -f Cargo.toml ] || ls ./*/Cargo.toml >/dev/null 2>&1; } && STACK="$STACK rust"
{ [ -f pyproject.toml ] || [ -f requirements.txt ] || [ -f setup.py ]; } && STACK="$STACK python"
[ -f go.mod ] && STACK="$STACK go"
STACK="${STACK# }"

# Pick an installer hint based on what's available.
if have brew; then PM="brew install"; elif have apt-get; then PM="sudo apt-get install"; else PM="(install manually)"; fi

# --- probe each tier ------------------------------------------------------- #
# Universal tiers (every repo benefits): sast, deps (CVEs), secrets.
sast_tool=""; have semgrep && sast_tool="semgrep"
# Dep-CVE scanning. osv-scanner / trivy are universal (lockfile-agnostic). The
# native scanners only count when their ecosystem's manifest is actually here —
# claiming "npm-audit" in a Rust repo would be exactly the false confidence this
# probe exists to kill.
deps_tool=""
if   have osv-scanner; then deps_tool="osv-scanner"
elif have trivy;       then deps_tool="trivy"
elif have pip-audit && { [ -f pyproject.toml ] || [ -f requirements.txt ]; }; then deps_tool="pip-audit"
elif [ -f package.json ] && have npm; then deps_tool="npm-audit"
elif have cargo-audit && { [ -f Cargo.toml ] || ls ./*/Cargo.toml >/dev/null 2>&1; }; then deps_tool="cargo-audit"; fi
secrets_tool=""; have gitleaks && secrets_tool="gitleaks"

# Type/lint tiers, only meaningful for a detected language.
types_node=""; { have tsc || ([ -d node_modules/.bin ] && [ -x node_modules/.bin/tsc ]); } && types_node="tsc"
types_py="";   have mypy && types_py="mypy"; [ -z "$types_py" ] && have pyright && types_py="pyright"
types_rust=""; have cargo && types_rust="cargo/clippy"

# --- emit ------------------------------------------------------------------ #
universal_live=0
[ -n "$sast_tool" ]    && universal_live=$((universal_live+1))
[ -n "$deps_tool" ]    && universal_live=$((universal_live+1))
[ -n "$secrets_tool" ] && universal_live=$((universal_live+1))

if [ "$JSON" = 1 ]; then
  bundled="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/skills/app-audit/references/detectors/greenloop.yml"
  [ -f "$bundled" ] && bundled_present=true || bundled_present=false
  printf '{\n'
  printf '  "stack": "%s",\n' "$STACK"
  printf '  "tiers": {\n'
  printf '    "sast":    {"live": %s, "tool": "%s"},\n'    "$([ -n "$sast_tool" ] && echo true || echo false)" "$sast_tool"
  printf '    "deps":    {"live": %s, "tool": "%s"},\n'    "$([ -n "$deps_tool" ] && echo true || echo false)" "$deps_tool"
  printf '    "secrets": {"live": %s, "tool": "%s"},\n'    "$([ -n "$secrets_tool" ] && echo true || echo false)" "$secrets_tool"
  printf '    "types":   {"node": "%s", "python": "%s", "rust": "%s"}\n' "$types_node" "$types_py" "$types_rust"
  printf '  },\n'
  printf '  "bundled_semgrep_ruleset": %s,\n' "$bundled_present"
  printf '  "universal_tiers_live": "%d/3"\n' "$universal_live"
  printf '}\n'
  [ "$universal_live" -eq 3 ] && exit 0 || exit 1
fi

bold(){ printf '\033[1m%s\033[0m\n' "$*"; }
row(){ # tier-label  tool-or-empty  install-hint
  if [ -n "$2" ]; then printf '  \033[32m✓\033[0m %-26s %s\n' "$1" "$2"
  else printf '  \033[31m✗\033[0m %-26s \033[33mmissing\033[0m — %s\n' "$1" "$3"; fi
}

bold "Greenloop detector readiness"
[ -n "$STACK" ] && printf '  detected stack: %s\n' "$STACK" || printf '  detected stack: (none — run inside a repo)\n'
echo
row "SAST (security/safety)"  "${sast_tool:+$sast_tool $(ver semgrep)}"   "$PM semgrep   (or: pipx install semgrep)"
row "Dependency CVEs"         "${deps_tool}"                              "$PM osv-scanner   (or trivy / pip-audit / npm)"
row "Secrets"                 "${secrets_tool:+$secrets_tool $(ver gitleaks)}" "$PM gitleaks"
case " $STACK " in *" node "*)   row "Types (node/ts)"  "$types_node" "npm i -D typescript" ;; esac
case " $STACK " in *" python "*) row "Types (python)"   "$types_py"   "pipx install mypy" ;; esac
case " $STACK " in *" rust "*)   row "Types (rust)"     "$types_rust" "rustup component add clippy" ;; esac
echo
if [ -n "$sast_tool" ]; then
  bundled="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/skills/app-audit/references/detectors/greenloop.yml"
  [ -f "$bundled" ] && printf '  bundled offline ruleset available: semgrep --config %s\n\n' "$bundled"
fi
printf '  universal tiers live: %d/3 ' "$universal_live"
if [ "$universal_live" -eq 3 ]; then printf '\033[32m(all grounded)\033[0m\n'
else printf '\033[33m(missing tiers degrade findings to judgement-only — lower confidence)\033[0m\n'; fi

# --- optional install ------------------------------------------------------ #
if [ "$INSTALL" = 1 ] && [ "$universal_live" -lt 3 ]; then
  echo
  if ! have brew; then echo "  --install needs Homebrew (brew). Install the tools manually with the hints above." >&2; exit 1; fi
  to_install=""
  [ -z "$sast_tool" ]    && to_install="$to_install semgrep"
  [ -z "$deps_tool" ]    && to_install="$to_install osv-scanner"
  [ -z "$secrets_tool" ] && to_install="$to_install gitleaks"
  printf '  About to run: brew install%s\n  Proceed? [y/N] ' "$to_install"
  read -r ans
  if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
    # shellcheck disable=SC2086
    brew install $to_install && echo "  done — re-run greenloop-doctor to confirm."
  else
    echo "  skipped."
  fi
fi

[ "$universal_live" -eq 3 ] && exit 0 || exit 1
