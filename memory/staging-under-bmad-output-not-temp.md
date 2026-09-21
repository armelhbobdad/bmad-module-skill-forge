---
created: "2026-03-17 22:45"
session: "e95bcf48-b3ad-46c7-9490-7389934ffffd"
source: claude-mem
source_table: both
source_ids: [1597, 1600, 1609]
---

# Workflow staging under _bmad-output, clones under system temp

Every skf-create-skill staging location is project-relative under the gitignored `_bmad-output/`: compile writes to `_bmad-output/{skill-name}/` (references/compile.md:27,39), fetch-docs to `_bmad-output/{skill-name}-docs/` (references/sub/fetch-docs.md:176) and fetch-temporal to `_bmad-output/{skill-name}-temporal/` (references/sub/fetch-temporal.md:68), and QMD `collection add` and step 7 promotion point at those paths. Only throw-away shallow git clones use `{system_temp}/skf-ephemeral-{skill-name}-{timestamp}/` (references/source-resolution-protocols.md:164, tier-degradation-rules.md:16, skf-update-skill/references/remote-source-resolution.md:63) and are deleted after extraction. A new step that stages files should keep to this split: the old step-03c-fetch-docs staged under `{system_temp}/skf-docs-{skill-name}/`, diverged from its sibling steps, and had to be realigned in PR #43 (05179fa9).
