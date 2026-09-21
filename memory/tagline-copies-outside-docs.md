---
created: "2026-03-20 01:30"
session: "a84b6d06-7d19-4ad8-b36f-4a9360c8df20"
source: claude-mem
source_table: observations
source_ids: [1936, 1937, 1938]
---

# Project tagline hand-copied in seven files

The tagline "Turn code and docs into instructions AI agents can actually follow" is duplicated by hand in README.md, `src/module.yaml` (`header:` shown in the BMad installer module picker), `package.json` `description` (npm registry), `.claude-plugin/marketplace.json` `description` (plugin marketplace), `tools/build-docs.js` (the llms.txt generator), `tools/cli/lib/ui.js` (the install banner) and `website/astro.config.mjs` (`tagline`). No validator covers them: a March 2026 rebrand that edited only README and docs left the old "AST-verified, provenance-backed" wording published in llms.txt, on npm and in the CLI banner until a review caught it. Any messaging change needs `grep -rn "<old tagline>" tools/ src/module.yaml package.json .claude-plugin/ website/ README.md` and all seven edited in the same commit.
