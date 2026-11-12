---
created: "2026-10-01 15:38"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# docs:build fails with a symlinked website/node_modules

In a scratch worktree whose `node_modules` and `website/node_modules` are symlinks to the main checkout's, `npm run docs:build` (`tools/build-docs.js`, which runs `npx astro build --root website`) fails with `[astro:build] Could not load <main checkout>/website/node_modules/@astrojs/starlight/components/Page.astro?astro&type=style&index=0&lang.css` and `No cached compile metadata found for ...`. Vite resolves the links to real paths outside the worktree root, and the CI link check `node tools/validate-docs-links.js --strict --require-build` (`.github/workflows/quality.yaml`) then fails too with `no build found, and --require-build was given`. It hit on 2026-10-01 and again on 2026-10-15 during a release replay, and replacing both links with real installs (`npm ci` and `npm ci --prefix website`, as CI does) made the build and the strict link check pass. So a docs build failure in a symlinked worktree comes from the setup, not a docs regression: install real dependencies there or build from the main checkout. Symlinks stay fine for `npm test` and `npm run quality`.
