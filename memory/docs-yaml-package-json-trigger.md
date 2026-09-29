---
created: "2026-04-04 22:06"
session: "7070fa3d-9a71-4237-8b63-c0f357f172e0"
source: claude-mem
source_table: observations
source_ids: [4395, 4399]
---

# docs.yaml builds a stable tag, so the version badge follows releases

The Starlight header version badge (`website/src/components/Header.astro` and `MobileMenuFooter.astro`) reads the root `package.json` at build time via `../../../package.json`; a client-side npm fetch was considered and rejected. Until #578, `.github/workflows/docs.yaml` redeployed on every push to main that touched `docs/**`, `website/**`, `tools/build-docs.js` or `package.json`, so the site showed docs for unreleased behaviour; the maintainer decided the docs deploy only after a release. docs.yaml now has no push trigger. After a stable release, release.yaml's "Deploy the docs site at the new tag" step runs `gh workflow run docs.yaml --ref main -f ref=vX.Y.Z` (the run is on main because the github-pages environment accepts deployments only from the default branch), and docs.yaml checks out and builds that tag, whose `package.json` carries the new version. A manual `gh workflow run docs.yaml` builds the latest stable tag; a tag placed on a pre-bump commit during a release recovery would deploy the old version badge.
