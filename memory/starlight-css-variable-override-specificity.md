---
created: "2026-03-06 14:23"
session: "16eaf640-7cea-416c-ab4d-6238288a3fd9"
source: claude-mem
source_table: session_summaries
source_ids: [196, 197]
---

# Starlight CSS-variable override specificity in website custom.css

The docs site (`website/`, Starlight ^0.37) once set `--sl-content-width: 100%` in `website/src/styles/custom.css` and the page layout differed between light and dark mode ("Why I have a different layout when I switch to dark mode?"). Starlight's own `components/Page.astro` sets `--sl-content-width: 67.5rem` on `html:not([data-has-sidebar])` (specificity 0,1,1), which beats a plain `:root` override (0,1,0) but loses to `:root[data-theme='dark']` (0,2,0), so the override only took effect in dark mode. Commit 02c10593 fixed it by deleting the override entirely; `custom.css` today declares its palette on `:root` and `:root[data-theme='dark']` only. Any future Starlight layout-variable override in `custom.css` must use a selector that wins in both themes (e.g. match `html:not([data-has-sidebar])` or higher) and be checked in both modes before shipping, because a `:root`-only override silently loses on no-sidebar pages in light mode.
