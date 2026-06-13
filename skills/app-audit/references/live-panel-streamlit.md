# Live Audit Panel — Streamlit UI

The audit skill produces a live status panel during execution. This is most useful when running app-audit from Claude Desktop (where rich rendering is limited) — a Streamlit app launched locally gives the user a real-time view of audit progress in a browser window.

This is optional — the audit also produces a text-mode summary that works everywhere. The Streamlit panel is for users who want a richer view.

---

## When to launch the panel

Launch the Streamlit panel when:

1. The user is running app-audit from Claude Desktop (not Claude Code)
2. The audit scope is substantial (3+ categories, or ≥30 checklist items)
3. The user hasn't opted out (e.g., set `audit.panel: false` in their preferences)

For audits in Claude Code, the panel is usually unnecessary — terminal text output is already rich. The text-mode summary at the end of execution is sufficient.

Always tell the user before launching:
> "I'll launch a Streamlit panel at http://localhost:8501 for live audit progress. You can keep this open in your browser while we work. Continue?"

---

## What to launch (the Streamlit script)

Create `.audit/panel.py` (or use an existing one if present) and write the Streamlit script. The script reads `.audit/run_state.json` — which the audit updates throughout Phase 3 — and renders the panel.

### Streamlit script template

```python
"""
app-audit live panel.
Renders the current audit run state from .audit/run_state.json.
Auto-refreshes every 2 seconds while the audit is running.
"""
import json
import time
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="App Audit — Live", page_icon="🔎", layout="wide")

STATE_PATH = Path(".audit/run_state.json")

def load_state():
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError:
        return None

state = load_state()

if state is None:
    st.info("Waiting for audit to start...")
    time.sleep(2)
    st.rerun()

# Header
st.title(f"🔎 App Audit — Round {state.get('round_number', '?')}")
st.caption(f"{state.get('project_name', 'Unknown project')} · Phase {state.get('current_phase', '?')}")

# Phase strip
phases = ["0 Baseline", "0.5 Cartography", "1 Setup", "2 Scope", "3 Execute", "4 Report", "5 Close"]
current_phase = state.get("current_phase", "0")
cols = st.columns(len(phases))
for col, phase in zip(cols, phases):
    phase_num = phase.split()[0]
    if phase_num < current_phase:
        col.success(phase)
    elif phase_num == current_phase:
        col.info(f"→ {phase}")
    else:
        col.text(phase)

st.divider()

# Pre-commit baseline
col1, col2 = st.columns(2)
with col1:
    st.subheader("Pre-commit baseline")
    baseline = state.get("pre_commit_baseline", {})
    if baseline:
        for check, status in baseline.items():
            icon = "✓" if status == "clean" or status == "pass" else "✗"
            st.text(f"{icon} {check}: {status}")
    else:
        st.text("Not yet run")

# Codemap state
with col2:
    st.subheader("Codemap")
    codemap = state.get("codemap_state", {})
    if codemap:
        st.text(f"Files mapped: {codemap.get('files_count', '?')}")
        st.text(f"State: {codemap.get('state', '?')}")
        warnings = codemap.get("warnings_count", {})
        if warnings.get("high", 0) > 0:
            st.error(f"{warnings['high']} high-severity warnings")
        elif warnings.get("medium", 0) > 0:
            st.warning(f"{warnings['medium']} medium-severity warnings")
        else:
            st.success("No warnings")
    else:
        st.text("Codemap not yet checked")

st.divider()

# Scope and currently checking
col3, col4 = st.columns(2)
with col3:
    st.subheader("Scope")
    scope = state.get("scope", [])
    for category in scope:
        name = category.get("name", "?")
        done = category.get("items_done", 0)
        total = category.get("items_total", 0)
        if done == total and total > 0:
            st.success(f"{name} — {done}/{total}")
        elif done > 0:
            st.info(f"{name} — {done}/{total} (in progress)")
        else:
            st.text(f"{name} — 0/{total}")

with col4:
    st.subheader("Currently checking")
    current_item = state.get("current_item", {})
    if current_item:
        st.markdown(f"**Item:** {current_item.get('id', '?')}")
        st.markdown(f"{current_item.get('description', '')}")
        files = current_item.get("files_examined", [])
        if files:
            st.caption(f"Files examined: {len(files)}")
            for f in files[-5:]:
                st.code(f, language=None)
    else:
        st.text("Idle")

st.divider()

# Findings so far
st.subheader(f"Findings so far ({len(state.get('findings', []))})")
findings = state.get("findings", [])

severity_colors = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪", "info": "🔵"}

for finding in findings:
    sev = finding.get("severity", "info")
    icon = severity_colors.get(sev, "⚫")
    location = finding.get("location", "?")
    title = finding.get("title", "?")
    with st.expander(f"{icon} {sev.upper()} · {location} · {title}"):
        st.markdown(finding.get("description", ""))
        if finding.get("blast_radius"):
            st.caption(f"Blast radius: {finding['blast_radius']}")
        st.markdown(f"**Suggested fix:** {finding.get('suggested_fix', '')}")

# Auto-refresh while audit running
if current_phase not in ("5", "complete"):
    time.sleep(2)
    st.rerun()
```

### Running the panel

When the audit decides to launch the panel:

1. Verify Streamlit is available: `python -c "import streamlit"`
2. If not installed, offer:
   > "Streamlit isn't installed. Install it with `pip install streamlit` and I'll launch the panel. Or continue with text-mode."
3. Write `.audit/panel.py` (overwrite any existing version with the current template)
4. Launch in the background: `streamlit run .audit/panel.py --server.headless true &`
5. Tell the user the URL and that the panel will auto-update

The Streamlit process runs in the background while the audit proceeds. The audit updates `.audit/run_state.json` after every checklist item, every finding, every phase transition. The panel reads that file and re-renders.

---

## What lives in run_state.json

This is the file the panel reads. The audit writes it as work progresses.

```json
{
  "schema_version": 1,
  "started_at": "2026-05-17T14:00:00Z",
  "round_number": 4,
  "project_name": "Your App",
  "current_phase": "3",
  "phase_started_at": "2026-05-17T14:08:00Z",

  "pre_commit_baseline": {
    "tests": "412/412 passing",
    "lint": "clean",
    "typecheck": "clean",
    "build": "success",
    "smoke": "3/3 passing"
  },

  "codemap_state": {
    "state": "refreshed_incrementally",
    "files_count": 247,
    "last_refresh_commit": "abc123def",
    "warnings_count": { "high": 1, "medium": 3, "low": 2 }
  },

  "scope": [
    { "name": "1 Schema integrity", "items_done": 8, "items_total": 8 },
    { "name": "3 Security", "items_done": 12, "items_total": 12 },
    { "name": "5 Concurrency", "items_done": 4, "items_total": 7 },
    { "name": "7 Spec compliance", "items_done": 0, "items_total": 23 }
  ],

  "current_item": {
    "id": "5.4",
    "description": "Row-level locking on message_pipeline_state status transitions",
    "files_examined": [
      "workers/categorize.rs",
      "workers/vectorize.rs",
      "workers/download.rs"
    ]
  },

  "findings": [
    {
      "severity": "critical",
      "location": "auth/refresh.ts:88",
      "title": "OAuth token in error log",
      "description": "When the refresh call fails, the error is logged via logger.error(err) and err contains the full request body including the refresh token.",
      "blast_radius": "14 files import this; tokens may leak via any error path",
      "suggested_fix": "Redact request bodies in error logging; strip tokens from errors before throwing."
    }
  ],

  "history": [
    { "round": 1, "date": "2026-04-12", "findings_count": 14, "fixed": 13 },
    { "round": 2, "date": "2026-04-26", "findings_count": 7, "fixed": 7 },
    { "round": 3, "date": "2026-05-03", "findings_count": 11, "fixed": 9 }
  ]
}
```

The audit updates this file:
- On every phase transition
- On every checklist item start/complete
- On every finding recorded
- On every codemap state change

Writes should be atomic — use temp-file + rename pattern so the panel never reads a half-written JSON.

---

## Text-mode fallback

When Streamlit isn't available or the user opts out, the audit produces text-mode status blocks at key transitions. Print blocks like this:

```
═══════════════════════════════════════════════════
APP AUDIT — Round 4 · Phase 3 (Execute)
Your App
───────────────────────────────────────────────────
Pre-commit baseline:   ✓ all clean
Codemap state:         247 files, refreshed incrementally
Codemap warnings:      1 high · 3 medium · 2 low

Scope progress:
  ✓ 1 Schema integrity      8/8
  ✓ 3 Security              12/12
  → 5 Concurrency           4/7 (in progress)
  · 7 Spec compliance       0/23

Findings so far: 6
  🔴 1 critical · 🟠 3 high · 🟡 2 medium

Currently checking: item 5.4 — row-level locking on
  message_pipeline_state status transitions
  Files examined: workers/categorize.rs, workers/vectorize.rs,
  workers/download.rs
═══════════════════════════════════════════════════
```

Print this:
- At the start of each phase
- Every ~5 checklist items completed in Phase 3
- When a Critical or High finding is recorded
- At final report

That's enough information density for text-mode users without flooding the terminal.

---

## Cleanup

After audit Phase 5 completes:

- Leave `.audit/run_state.json` for review (don't delete — it's part of the round's record)
- Leave the Streamlit process running so the user can review the panel
- Tell the user the panel URL and that they can close it when done
- The next audit run will overwrite `run_state.json` with a fresh round

If the panel needs to be killed manually: `pkill -f "streamlit run .audit/panel.py"`.

---

## When NOT to use the panel

- The user is on a slow or low-spec machine where Streamlit launch would be intrusive
- The user has explicitly declined panel use in earlier audits
- The audit is small (single category, <10 checklist items) — text-mode is fine
- The user is in a constrained environment (CI, headless server) where opening a browser would be useless

Default to launching for Claude Desktop audits with substantial scope. Default to text-mode for Claude Code audits. Both modes coexist; the user can switch.
