---
created: "2026-03-14 14:15"
session: "cdec0d4f-5790-4bdf-b019-c0dee4ca15d1"
source: claude-mem
source_table: observations
source_ids: [1019]
---

# Docs describe current capabilities, never removed features

When the setup-forge auto-index feature was replaced by the progressive QMD collection registry (commit 4d74d96a, 2026-03), the user ruled that docs and articles must not mention the removed feature at all, not even as "formerly": "It is not necessary to mention the old auto-index feature. We should stay focus on the innovation of using SKF with deep tier mode." User-facing material — docs/*.md, README.md, Medium articles, pitch copy — describes what SKF does now; a removed capability belongs in CHANGELOG.md only. Nothing in CONTRIBUTING.md's docs guidance records this, so it is easy to add a well-meant "this replaces the old X" note that the user does not want. (`src/skf-setup/references/auto-index.md` still exists today, but it is the "QMD + CCC Registry Hygiene" step, not the old feature.)
