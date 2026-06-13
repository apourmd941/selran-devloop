# Loop UI

Small local dashboard for launching `cli/autoloop` and watching the workflow as
`cartographer` stages 1-4, `pre-commit-verification`, `app-audit`, `audit-fix`,
and `loop`.

Run it from the DevLoop repo:

```bash
python3 ui/devloop_ui.py
```

The default mode is `dry-run`, which exercises the loop without API calls or PRs.
`host` and `sandbox` modes use the existing `autoloop` behavior and prerequisites.
