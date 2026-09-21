---
created: "2026-04-25 04:54"
session: "8c30e5aa-9220-4ff5-b7b5-41da9b67d186"
source: claude-mem
source_table: observations
source_ids: [7482, 7486, 7505]
---

# STABILITY.md and RELEASING.md hidden under docs/_internal/

`docs/_internal/STABILITY.md` and `docs/_internal/RELEASING.md` are deliberately off the published site: they were moved there from `docs/` (commit 784921c4) and their `stability`/`releasing` entries removed from the sidebar in `website/astro.config.mjs`, so no `/stability/` or `/releasing/` route exists. The user chose to hide both rather than only the release procedure: **"hide both"**. They stay in the repo as maintainer references reached from `CONTRIBUTING.md` § Releasing and from comments in `.github/workflows/release.yaml`; README's own links to them were dropped later (b3e4e31e), so nothing user-facing points at STABILITY.md any more — do not re-add sidebar entries or move the files back to `docs/` to "fix" that. `release-audits/` keep the old `docs/STABILITY.md` paths as historical records and are not to be rewritten.
