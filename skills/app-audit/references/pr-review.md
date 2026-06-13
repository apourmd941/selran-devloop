# PR / diff-scoped review — recipes

Concrete commands for the change-scoped audit (Step 2.4) and finding
publication (Step 5.3). Everything degrades gracefully: if a CLI or auth is
missing, fall back to the local-only behavior and tell the user — never block
the audit on a missing integration.

## 1. Resolve the change-set

Pick the base ref, then list changed files. Reading is limited to these files
plus their one-level blast-radius dependents (cartographer `imported_by` /
`called_by`).

```bash
# Branch vs default branch (most common "review my changes")
BASE=$(git merge-base HEAD origin/main 2>/dev/null || git merge-base HEAD main)
git diff --name-only "$BASE"...HEAD

# Last N commits
git diff --name-only HEAD~N...HEAD

# A specific GitHub PR (preferred when gh is authed)
gh pr diff <number> --name-only
# …and the full patch for line context:
gh pr diff <number>

# GitLab MR
glab mr diff <number>
```

Detector runs (Step 3.0) can be scoped too — e.g. `semgrep --baseline-commit
"$BASE"` reports only newly-introduced hits, which lines up with provenance.

## 2. Post findings as PR review comments (GitHub)

A summary comment plus line-anchored review comments. Show the user the text
first unless running in CI with explicit post intent.

```bash
# Summary comment — lead with the trust signals
gh pr comment <number> --body "$(cat <<'EOF'
### Greenloop audit — N findings (M new, P pre-existing)
Challenge pass: M confirmed, K refuted (removed). Detectors: semgrep, osv-scanner.
<one line per confirmed finding: severity · file:line · title · confidence>
EOF
)"

# Line-anchored review comment (requires the PR's head SHA + file + line)
HEAD_SHA=$(gh pr view <number> --json headRefOid -q .headRefOid)
gh api -X POST "repos/{owner}/{repo}/pulls/<number>/comments" \
  -f body="**[High · 0.82]** Missing transaction around the multi-table write — …" \
  -f commit_id="$HEAD_SHA" \
  -f path="workers/sync.ts" \
  -F line=142 -f side=RIGHT
```

GitLab equivalent: `glab mr note <number> -m "<summary>"` for the summary;
discussion API for line notes.

**Only post grounded, challenge-surviving findings.** Never post Info/advisory
or refuted findings — a noisy PR review is worse than none.

## 3. File findings as issues (idempotent)

For tracked-not-now findings. De-dupe by title against open issues first.

```bash
TITLE="[High] Missing transaction in worker.sync"
# Skip if an open issue with this title already exists
if ! gh issue list --state open --search "in:title \"$TITLE\"" --json title -q '.[].title' | grep -qxF "$TITLE"; then
  gh issue create --title "$TITLE" \
    --body "<the full finding block from AUDIT_LOG.md>" \
    --label audit --label "severity:high" --label "category:concurrency"
fi
```

Create the labels once if absent (`gh label create audit -c FBCA04` etc.).
GitLab: `glab issue create`.

## 4. CI mode (label-triggered GitHub Actions)

A workflow that runs the audit on PRs labeled `greenloop-review` and posts the
result. Non-interactive: the audit must run with an explicit post intent and
never prompt. (This is a template the user drops into `.github/workflows/`.)

```yaml
name: greenloop-pr-review
on:
  pull_request:
    types: [labeled]
permissions:
  contents: read
  pull-requests: write
  issues: write
jobs:
  review:
    if: github.event.label.name == 'greenloop-review'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }          # full history → git-blame provenance
      - name: Run greenloop PR audit
        env: { GH_TOKEN: ${{ github.token }} }
        run: |
          # invoke the agent headless with the PR scope + --post,
          # e.g. `claude -p "audit PR ${{ github.event.number }} and post findings"`
          echo "wire to your headless Claude Code runner here"
```

`fetch-depth: 0` is required — a shallow clone has no blame data, so provenance
degrades to "unknown" (Step 4.1.3).

## 5. Worktree-isolated fixes (for audit-fix)

When audit-fix runs on a PR review, isolate the fixes in a dedicated worktree so
the user's working tree is never touched and the fix branch is clean:

```bash
git worktree add -b greenloop/fix-pr-<n> ../gl-fix-<n> "$BASE"
# audit-fix applies + per-fix-verifies inside ../gl-fix-<n>
# on success: push the branch / open a fix PR; on failure: remove the worktree
git worktree remove ../gl-fix-<n>
```

## 6. Conventional commits

When greenloop creates commits (fix branches, issue-driven fixes), use
Conventional Commits so changelogs/release tooling stay clean:

```
fix(concurrency): add row-lock before status transition (greenloop #142)
chore(audit): record round 3 coverage
```

Type from the finding category: `fix` for bugs/safety/concurrency/security,
`perf` for performance, `test` for coverage, `refactor` for structure, `docs`
for doc findings. Scope = the audit category or touched module. Reference the
finding/issue id in the footer.
