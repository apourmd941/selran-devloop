# Greenloop hooks — enforcement layer

Greenloop ships three Claude Code hooks (`hooks/hooks.json`) that turn its
disciplines from guidelines into guarantees. They are **inert for normal work**
— each does nothing unless a greenloop workflow is active — so installing the
plugin doesn't change how you edit code day to day.

| Hook | Event | What it does | Default |
|---|---|---|---|
| `audit-readonly-guard.sh` | PreToolUse (Edit/Write/MultiEdit) | Blocks source edits **while an app-audit review is in progress** so the auditor stays read-only and objective | On (but only acts during an audit) |
| `auto-format.sh` | PostToolUse (Edit/Write/MultiEdit) | Formats the file just edited (rustfmt / ruff / gofmt / prettier) | **Off** — opt in with `GREENLOOP_AUTOFORMAT=1` |
| `session-staleness.sh` | SessionStart | Warns if the codemap is behind HEAD or `AUDIT_LOG.md` has open findings; cleans a stale audit marker | On (silent unless there's something to say) |

## The read-only guard (the headline)

app-audit raises a marker (`.audit/.audit-active`) at Phase 3 and clears it at
Phase 5. While it's up, the guard denies edits to source files — but always
allows writes to `.audit/` and `AUDIT_LOG.md` (the audit records its own
findings). A reviewer that can quietly fix as it goes anchors on its own
narrative and stops finding things; this makes "the auditor reviews, audit-fix
remediates" a hard boundary, the way eight-eyes and mumei enforce it.

Properties:
- **Inert outside audits.** No marker → every edit passes. audit-fix runs after
  the window closes, so fixing is never blocked.
- **Escape hatch.** `GREENLOOP_BYPASS=1` lets any edit through; after a few
  blocked attempts the denial message reminds you of it.
- **Crash-safe.** A marker older than 6h (abandoned session) is auto-cleaned by
  the guard and by SessionStart — it can never wedge you permanently.
- **Fail-open.** Missing `jq`, an odd path, or any uncertainty → the edit is
  allowed. A review tool must never block your editor.

## Environment variables

| Var | Effect |
|---|---|
| `GREENLOOP_BYPASS=1` | Disable the read-only guard for this session |
| `GREENLOOP_AUTOFORMAT=1` | Enable post-edit auto-formatting |

## Disabling

Hooks are opt-in at the plugin level — remove or rename `hooks/hooks.json` to
drop the layer entirely, or set the env vars above to tune individual hooks.
The skills work fully without the hooks; the hooks only add enforcement.
