---
created: "2026-03-06 18:31"
session: "03fbbf9a-9dfa-4a74-92c9-43534d64de7d"
source: claude-mem
source_table: both
source_ids: [562, 572]
---

# GitHub Pages source must be GitHub Actions, not a branch

The docs site at <https://armelhbobdad.github.io/bmad-module-skill-forge/> is built by `.github/workflows/docs.yaml` (`actions/upload-pages-artifact` + `actions/deploy-pages`), but that only takes effect when the repository setting Settings → Pages → Build and deployment → Source is "GitHub Actions" (`gh api repos/<owner>/<repo>/pages` shows `build_type: "workflow"`). With the default "Deploy from a branch" (`build_type: "legacy"`) GitHub silently Jekyll-renders `docs/` from `main` instead: docs.yaml still runs green and uploads the Astro artifact, yet the live site serves raw markdown with links missing the `/bmad-module-skill-forge/` base path. The fix was made by hand in the repo settings ("I did it manually. check if everything is good"). It is a repository setting outside the code, so it must be redone on a fork or a new repo, and it is the first thing to check before debugging docs.yaml, `tools/build-docs.js` or `website/astro.config.mjs`.
