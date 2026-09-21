---
created: "2026-03-21 18:43"
session: "f2ad790b-1d74-4c13-b83e-7656902ab042"
source: claude-mem
source_table: observations
source_ids: [2028, 2029, 2031]
---

# Docs page slugs match their sidebar labels

Docs page URL slugs must match the meaning of their sidebar label: a page labelled "How It Works" served at `/architecture` was rejected by the user — "The navigation url to the page "How It Works" is /architecture. It is not aligned with the semantic of the other pages" — and became `docs/how-it-works.md` at `/how-it-works/` (a separate `docs/architecture.md` deep-dive now sits under the label 'Architecture'). Renaming a docs page therefore means `git mv docs/<old>.md docs/<new>.md`, changing that entry's `slug` in the `website/astro.config.mjs` sidebar, fixing cross-links inside `docs/` (`npm run validate:docs-links` catches those), and hand-editing the `armelhbobdad.github.io/bmad-module-skill-forge/<slug>/` URLs in `README.md`, which neither `tools/validate-docs-links.js` nor `tools/validate-doc-links.js` scans (both walk `docs/` only). Changing only the label leaves the old slug live and the mismatch invisible to every validator.
