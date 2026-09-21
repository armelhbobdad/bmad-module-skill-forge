---
created: "2026-03-21 18:28"
session: "f2ad790b-1d74-4c13-b83e-7656902ab042"
source: claude-mem
source_table: observations
source_ids: [2024, 2037, 2041]
---

# Docs CI must install website/ dependencies separately

`website/` has its own `package.json` and `package-lock.json`, separate from the root, and `npm run docs:build` (`tools/build-docs.js` → `npx astro build --root website`) resolves `website/astro.config.mjs` imports from `website/node_modules`. When the astro-mermaid integration merged with only a root `npm ci` in `.github/workflows/docs.yaml`, main broke with `[vite] (ssr) Error when evaluating SSR module .../website/astro.config.mjs: Cannot find module 'astro-mermaid' imported from .../website/astro.config.mjs` while the build was green locally. The fix is the `Install website dependencies` step (`npm ci --prefix website`) that now sits between root `npm ci` and `docs:build` in both `docs.yaml` and `quality.yaml`; it is not redundant, and every new `website/` dependency relies on it.
