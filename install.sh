#!/usr/bin/env bash
# Selran DevLoop — friendly installer.
#
# Lets the user pick exactly what they want:
#   - one or more of the five methodology skills (standalone), OR
#   - the full DevLoop engine (skills + the autonomous run loop driver).
#
# Skills are copied to ~/.claude/skills/ (where Claude Code loads them from).
# The DevLoop engine is run in-place from this repo (./cli/autoloop run ...).
#
# Usage:
#   ./install.sh                  # interactive picker (default)
#   ./install.sh --all            # install all 5 skills, non-interactive
#   ./install.sh --devloop        # install full engine, non-interactive
#   ./install.sh --skill <name>   # install one skill by name, non-interactive
#                                 # (cartographer | pre-commit-verification | spec-bootstrap | app-audit | audit-fix)
#   ./install.sh --doctor         # report which audit detectors are installed (--doctor --install to add them)
#   ./install.sh -h | --help      # show this menu without installing

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$REPO_DIR/skills"
SKILLS_DEST="$HOME/.claude/skills"

# --------------------------------------------------------------------------- #
# Pretty output
# --------------------------------------------------------------------------- #
bold() { printf '\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
err()  { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; }
hr()   { printf -- '----------------------------------------------------------------\n'; }

# --------------------------------------------------------------------------- #
# Install one skill (copy source -> ~/.claude/skills/<name>)
# --------------------------------------------------------------------------- #
install_skill() {
  local name="$1"
  if [[ ! -d "$SKILLS_SRC/$name" ]]; then
    err "skill source not found: $SKILLS_SRC/$name"
    return 1
  fi
  mkdir -p "$SKILLS_DEST"
  rm -rf "$SKILLS_DEST/$name"
  cp -R "$SKILLS_SRC/$name" "$SKILLS_DEST/$name"
  local v
  v="$(grep -E '^version:' "$SKILLS_DEST/$name/SKILL.md" 2>/dev/null | head -1 | awk '{print $2}')"
  ok "$name (${v:-unknown}) → $SKILLS_DEST/$name"
}

install_all_skills() {
  bold "Installing the 5 methodology skills..."
  install_skill cartographer
  install_skill pre-commit-verification
  install_skill spec-bootstrap
  install_skill app-audit
  install_skill audit-fix
}

# --------------------------------------------------------------------------- #
# Detector readiness — app-audit's grounded findings need real analyzers.
# Informational: never blocks the install, just reports what's missing.
# --------------------------------------------------------------------------- #
check_detectors() {
  echo
  bold "Checking deterministic detectors (app-audit grounds findings in these)..."
  if [[ -x "$REPO_DIR/scripts/greenloop-doctor.sh" ]]; then
    bash "$REPO_DIR/scripts/greenloop-doctor.sh" || true
    echo
    echo "  Missing a tier? app-audit still runs, but those findings are"
    echo "  judgement-only (lower confidence). Install the universal ones with:"
    echo "    $REPO_DIR/scripts/greenloop-doctor.sh --install"
  else
    warn "greenloop-doctor not found — skipping detector check"
  fi
}

# --------------------------------------------------------------------------- #
# Full DevLoop engine: skills + prereq checks + usage hint
# --------------------------------------------------------------------------- #
install_devloop_engine() {
  install_all_skills
  echo
  bold "Checking DevLoop engine prerequisites..."

  if command -v python3 >/dev/null 2>&1; then
    ok "python3: $(python3 --version 2>&1)"
  else
    err "python3 not found — required to run the loop driver"
    return 1
  fi

  if python3 -c "import claude_agent_sdk" 2>/dev/null; then
    ok "claude_agent_sdk: installed"
  else
    warn "claude_agent_sdk not installed — install with: pip install claude-agent-sdk"
  fi

  if command -v gh >/dev/null 2>&1; then
    ok "gh CLI: $(gh --version 2>/dev/null | head -1)"
    if gh auth status >/dev/null 2>&1; then
      ok "gh auth: signed in"
    else
      warn "gh CLI not authenticated — run: gh auth login"
    fi
  else
    warn "gh CLI not found — required to open the PR (install: brew install gh)"
  fi

  if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    ok "ANTHROPIC_API_KEY: set"
  else
    warn "ANTHROPIC_API_KEY not set — export it in your shell before a live run"
  fi

  echo
  hr
  bold "DevLoop installed. To run autonomously on a repo:"
  echo
  echo "  cd $REPO_DIR"
  echo "  ./cli/autoloop run /path/to/target-repo --host"
  echo
  echo "First-time onboarding for a new target repo (one config file):"
  echo
  echo "  mkdir -p /path/to/target-repo/.devloop"
  echo "  cp $REPO_DIR/templates/autoloop.toml.example \\"
  echo "     /path/to/target-repo/.devloop/autoloop.toml"
  echo "  \$EDITOR /path/to/target-repo/.devloop/autoloop.toml"
  echo
  echo "  (then run the autoloop command above)"
  hr
}

# --------------------------------------------------------------------------- #
# Interactive menu
# --------------------------------------------------------------------------- #
show_menu() {
  cat <<'MENU'

Selran DevLoop — installer
==========================

Pick what to install. Each option explains what you get.

  1) cartographer (skill, standalone)
       Builds a persistent codemap of any codebase
       (.codemap/*.json — structure, dependencies, functions, warnings).
       Use it to map a repo, find dupe / unused files, or feed downstream tools.

  2) pre-commit-verification (skill, standalone)
       Runs unit/integration tests, lint, type-check, build, format — plus a
       runtime smoke harness (HTTP health, migration idempotency, webview e2e,
       provider mocks, env probe). Catches "all tests pass but the app fails
       when actually launched."

  3) spec-bootstrap (skill, standalone)
       Reconstructs a design spec for an app that never had one: derives
       observed behavior from the code, interviews you to separate intent
       from accident, writes a provenance-marked SPEC.md app-audit can use.

  4) app-audit (skill — bundles cartographer + pre-commit-verification + spec-bootstrap)
       Convergent codebase audit: schema, security, concurrency, resource
       bounds, spec compliance, ops, test coverage with acceptance mapping,
       diagnosability. Folds pre-commit + smoke results into a persistent
       AUDIT_LOG.md so audits converge across rounds.

  5) audit-fix (skill — bundles all of the above)
       Applies fixes for findings from app-audit safely: per-fix verification
       vs. baseline, adversarial re-verification, revert-on-fail,
       blast-radius-aware ordering via cartographer's call graph.

  A) ALL five skills (recommended for methodology-only use)

  D) Full DevLoop engine (autonomous run loop)
       Installs the 5 skills above + the `autoloop` runner. Cuts an isolated
       worktree branch, runs cartographer → app-audit → audit-fix → re-audit
       until green, then opens a reviewable PR. Your base branch is never
       touched. Verifies Python / Agent SDK / gh / API key.

  q) quit (install nothing)

MENU
}

# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
main() {
  case "${1:-}" in
    --all)
      install_all_skills
      check_detectors
      echo
      bold "Done. Restart Claude Code if it's running so the new skills load."
      echo "First run: open any repo and say \"quick audit\" (see QUICKSTART.md)."
      exit 0
      ;;
    --doctor)
      bash "$REPO_DIR/scripts/greenloop-doctor.sh" "${@:2}"
      exit $?
      ;;
    --devloop)
      install_devloop_engine
      exit 0
      ;;
    --skill)
      [[ $# -ge 2 ]] || { err "usage: $0 --skill <name>"; exit 2; }
      bold "Installing skill: $2"
      install_skill "$2"
      exit 0
      ;;
    -h|--help)
      show_menu
      exit 0
      ;;
    "")
      ;;  # fall through to interactive
    *)
      err "unknown flag: $1"
      err "try: $0 --help"
      exit 2
      ;;
  esac

  show_menu
  read -rp "Your choice [1/2/3/4/5/A/D/q]: " choice
  echo
  case "$choice" in
    1) bold "Installing cartographer..."; install_skill cartographer ;;
    2) bold "Installing pre-commit-verification..."; install_skill pre-commit-verification ;;
    3) bold "Installing spec-bootstrap..."; install_skill spec-bootstrap ;;
    4)
      bold "Installing app-audit (with its dependencies)..."
      install_skill cartographer
      install_skill pre-commit-verification
      install_skill spec-bootstrap
      install_skill app-audit
      check_detectors
      ;;
    5)
      bold "Installing audit-fix (with its dependencies)..."
      install_skill cartographer
      install_skill pre-commit-verification
      install_skill spec-bootstrap
      install_skill app-audit
      install_skill audit-fix
      check_detectors
      ;;
    A|a) install_all_skills; check_detectors ;;
    D|d) install_devloop_engine ;;
    q|Q) echo "no changes."; exit 0 ;;
    *) err "unknown choice: $choice"; exit 2 ;;
  esac

  echo
  bold "Done. Restart Claude Code if it's running so the new skills load."
}

main "$@"
