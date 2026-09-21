---
created: "2026-06-01 20:06"
session: "b80a57cb-2940-450e-9ffb-35e6c9e3019d"
source: claude-mem
source_table: observations
source_ids: [14081, 14082, 14104, 14110]
---

# Docs page titles are frontmatter Title Case

Pages under `docs/` carry their title in YAML frontmatter (Starlight renders it; there is no body H1, so `grep '^# ' docs/*.md` only hits code blocks) and every title is Title Case: `Forge-Auto`, `Getting Started`, `BMAD Synergy`. That applies to lowercase command aliases too — the user rejected a page titled `deepwiki` ("the deepwiki page title should start with "D"") and the fix capitalised the frontmatter title, the `website/astro.config.mjs` sidebar label and sentence-leading prose while the command itself stayed lowercase. The alias has since been renamed and the same split holds: page title and sidebar label `Forge-Auto`, command `@Ferris forge-auto`.
