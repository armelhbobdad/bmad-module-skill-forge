---
created: "2026-04-04 22:06"
session: "7070fa3d-9a71-4237-8b63-c0f357f172e0"
source: claude-mem
source_table: observations
source_ids: [4395, 4399]
---

# docs.yaml package.json trigger keeps the version badge current

The Starlight header version badge (`website/src/components/Header.astro` and `MobileMenuFooter.astro`) reads the root `package.json` at build time via `../../../package.json` rather than fetching npm at runtime (the client-side registry fetch was considered and rejected). That is why `.github/workflows/docs.yaml` lists `package.json` in its `on.push.paths` alongside `docs/**`, `website/**` and `tools/build-docs.js`: a release lands as a bot PR that bumps `package.json` on main, and that push is what redeploys the site with the new version. Dropping `package.json` from the trigger makes a release publish to npm while the site shows the old version until an unrelated docs commit.
