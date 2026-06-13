---
meta:
  project: Greenloop UI
  date: 2026-06-12
  version: 1
direction: technical-minimal
color:
  bg: "#FBFBFA"          # near-white, warm-cool neutral
  surface: "#FFFFFF"
  surface_2: "#F4F4F1"   # recessed panels, toolbar
  fg: "#1A1C1A"
  fg_muted: "#646A64"
  border: "#E4E4DE"
  accent: "#1F7A4D"      # forest green — the "runs until green" identity
  accent_hover: "#176039"
  # severity ramp — distinct, colorblind-considerate, used as left-borders + chips
  crit: "#B3261E"
  high: "#BC571B"
  med: "#9A7B0A"
  low: "#2F6DB3"
  info: "#6B6E76"
  dark:
    bg: "#121413"
    surface: "#1A1D1B"
    surface_2: "#22262300"  # see note: rgba in CSS
    fg: "#E7E9E5"
    fg_muted: "#9AA09A"
    border: "#2C302D"
    accent: "#4FB07C"
    accent_hover: "#6BC494"
    crit: "#E5685F"
    high: "#E0894A"
    med: "#CFAE3D"
    low: "#6EA8E0"
    info: "#9AA09A"
type:
  # no-CDN / single-file constraint → system stacks only (honest, fast, offline)
  display: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif'
  body: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif'
  mono: 'ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace'
  scale: "12 / 13 / 15 / 19 / 24"
  leading: 1.5
  tracking_caps: "0.06em"   # uppercase eyebrow labels
spacing:
  base_unit: 4
  radius: 8
  radius_sm: 6
motion:
  duration: "150ms"
  easing: "cubic-bezier(0.2, 0, 0, 1)"
  reduced_motion: respect
personality: >
  Greenloop is a security auditor; its UI should read like an instrument, not a
  brochure. Data is monospaced and dense; chrome is quiet system-sans. The green
  is the product's promise (the loop that runs until green) used with restraint —
  one accent, never decoration. Severity is the only place color raises its
  voice, because that is the one thing a reviewer scans for. Everything is a view
  of status.json: honest, regenerable, never a second source of truth.
---

# Design intent

The dashboard is a **findings workbench**, not a poster. A reviewer opens it to
answer three questions fast: *what's still open, how bad, and why*. So:

- **Type** is split: monospace for the load-bearing data (file:line, rule ids,
  counts), system-sans for labels and prose. This is the Linear/Stripe-console
  voice — dense but calm — done with zero webfonts so the file stays
  single-file, offline, and instant.
- **Color** is disciplined to one green accent plus a five-step severity ramp.
  The accent marks *the product* (header, active filter, links); severity marks
  *the findings*. Nothing else is colored. A reviewer's eye goes straight to the
  red.
- **Spatial logic** is a tight 4px grid, 8px radius, hairline borders. Columns
  and cards, not cards-in-cards. Density over whitespace — a real audit has 40
  findings and they must all be scannable without scrolling a mile.
- **Motion** is near-absent: 150ms on the drawer and filter transitions, and
  fully off under `prefers-reduced-motion`. An instrument doesn't bounce.

Three things to remember: the **green wordmark**, the **severity-striped finding
cards**, and the **drill-in drawer** that turns a scoreboard into a tool you
work from.
