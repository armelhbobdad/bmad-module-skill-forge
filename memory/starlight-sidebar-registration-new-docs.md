---
created: "2026-04-23 04:30"
session: "75a1a950-9e18-4517-8c49-31176db97824"
source: claude-mem
source_table: observations
source_ids: [6923, 6931, 13553, 14116]
---

# Starlight sidebar registration for new docs pages

The site nav is the hand-maintained `sidebar:` array in `website/astro.config.mjs` (Why / Try / Reference buckets, one `{ label, slug }` per page). A new `docs/*.md` page builds, passes `npm run validate:docs-links` and `npm run validate:refs`, and is reachable by direct URL, but stays invisible in the nav until its slug is added there — no validator checks sidebar coverage (`tools/validate-docs-links.js` only hashes `astro.config.mjs` as a build input) and CONTRIBUTING.md's docs section does not mention it. It has bitten three times: STABILITY.md/RELEASING.md shipped unregistered (v1.0.0 pre-flight gap H4), the deepwiki page (now `docs/forge-auto.md`) shipped orphaned until review added it to the Try bucket, and `docs/campaign.md` was missing from Try. Pages under `docs/_internal/` are deliberately excluded from the Starlight content collection by the underscore convention and must not be registered.
