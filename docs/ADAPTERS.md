# Running Greenloop outside Claude Code — adapters

The five Greenloop skills are plain-markdown methodology. Any agent CLI that
can read instructions can run the loop; what differs per host is **how the
instructions get loaded** and **how much of the enforcement layer exists**.

## What's portable vs. Claude Code-only

| Layer | Portable? |
|---|---|
| The five skills (cartographer, spec-bootstrap, pre-commit-verification, app-audit, audit-fix) | **Yes** — plain markdown + reference recipes; the workflows are host-agnostic |
| `.audit/` artifacts (AUDIT_LOG, status.json, TECHNICAL_DEBT, chronicle, learned rules, dashboard) | **Yes** — files on disk, produced by following the skills |
| Hooks (read-only audit window, staleness warnings — `hooks/`) | **No** — Claude Code plugin hooks. Other hosts rely on the skills' discipline without hard enforcement |
| Reviewer/challenger subagents (`agents/`) | **No** — Claude Code agent definitions. Elsewhere, app-audit's sequential mode and self-challenge fallbacks apply (they're built into the skills) |
| Selran Hub live panel | Works with any host that can `curl` localhost |

## Per-host installation

### Claude Code (full product)

```
/plugin marketplace add apourmd941/selran-devloop
/plugin install greenloop@selran
```

Skills + hooks + subagents — the complete enforcement story.

### OpenAI Codex CLI

```bash
scripts/install-codex-skills.sh     # copies the 5 skills to ~/.codex/skills/
```

Backs up any existing copies first; restart Codex afterwards. Codex loads
skills automatically from that directory.

### AGENTS.md hosts (OpenCode, Cursor, and most newer agent CLIs)

```bash
scripts/export-agent-skills.sh --agents-md          # writes GREENLOOP-AGENTS.md
```

Then wire the bundle in the host's own way — typically: include it from your
project's `AGENTS.md` (`See GREENLOOP-AGENTS.md for the audit/fix
methodology`), or paste the relevant skill section into the host's rules file
(Cursor: a rule under `.cursor/rules/`). The bundle strips frontmatter,
carries all five skills with their versions, and **cites** reference recipes
rather than inlining them — keep a clone of this repo around for the deep
recipes (`skills/<skill>/references/`).

### Any host with a skills directory

```bash
scripts/export-agent-skills.sh --copy <that-host's-skills-dir>
```

Copies the five skill directories (SKILL.md + references) verbatim.

## Honest expectations on other hosts

- **The discipline is in the text, not the host.** The read-only audit window,
  for example, is a hard guarantee in Claude Code (PreToolUse hook) and a
  strongly-worded instruction elsewhere. The skills are written to work as
  instructions alone — but Claude Code is the reference environment.
- **Subagent steps degrade by design.** Every step that prefers a subagent
  (blind challenge, parallel reviewers, blind test authoring) specifies its
  single-agent fallback inline. Nothing breaks; independence weakens.
- **The multi-model layer inverts here:** on another host, *Claude* can be the
  second opinion — the cross-provider protocol in
  `skills/app-audit/references/multi-model.md` is symmetric (the same
  privacy gate applies in both directions).
- Keep versions in sync: re-run the installer/exporter after updating the
  repo; a tagged release pins a known-good combination of all five skills.
