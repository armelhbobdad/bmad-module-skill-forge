---
created: "2026-03-14 13:58"
session: "cdec0d4f-5790-4bdf-b019-c0dee4ca15d1"
source: claude-mem
source_table: both
source_ids: [1009]
---

# No cognee mentions in qmd-registry.md

`src/knowledge/qmd-registry.md` must not name cognee. The user ruled: "Do not explicitly mention cognee in @src/knowledge/qmd-registry.md", and the registry-schema examples were rewritten to a generic `my-lib` skill (`my-lib-extraction`, `my-lib-brief`, `{skill-name}-…` placeholders). The scope is that one file only: cognee remains the worked example in README.md, docs/concepts.md and seven other src/ reference files (e.g. src/knowledge/version-paths.md, src/skf-quick-skill/references/resolve-target.md), so do not 'harmonize' qmd-registry.md back to cognee when touching its examples.
