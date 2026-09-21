---
created: "2026-04-21 05:44"
session: "d6ad714a-7854-4565-9252-30547faff1fa"
source: claude-mem
source_table: both
source_ids: [6695, 6706]
---

# STABILITY.md links to unshipped files use absolute GitHub URLs

`docs/` ships in the npm tarball but `.npmignore` excludes `test/` and root-level `*.md`, so `test/schema/agent.js` and `CHANGELOG.md` do not exist under `node_modules/bmad-module-skill-forge/`. Relative links from `docs/_internal/STABILITY.md` to those files would be dead for package consumers, so its References section (lines 120-123) deliberately uses absolute `https://github.com/armelhbobdad/bmad-module-skill-forge/blob/main/...` URLs for `CHANGELOG.md`, `tools/cli/lib/platform-codes.yaml` and `test/schema/agent.js`, while the link to `RELEASING.md` stays relative because it sits in the same shipped directory. A link-hygiene or "make links relative" pass (including `tools/fix-doc-links.js` style rewrites) must not convert these back, and the same rule applies to any shipped doc that links to a path `.npmignore` excludes.
