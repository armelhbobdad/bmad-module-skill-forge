---
created: "2026-03-17 22:45"
session: "e95bcf48-b3ad-46c7-9490-7389934ffffd"
source: claude-mem
source_table: both
source_ids: [1597, 1600, 1609]
---

# Workflow staging under _bmad-output, clones under system temp

Every skf-create-skill staging location is project-relative under the gitignored `_bmad-output/`: compile writes to `_bmad-output/.skf-stage/{skill-name}/` (references/compile.md, Rules and §1a), fetch-docs to `_bmad-output/{skill-name}-docs/` (references/sub/fetch-docs.md §5b) and fetch-temporal to `_bmad-output/{skill-name}-temporal/` (references/sub/fetch-temporal.md §3), and QMD `collection add` and step 7 promotion point at those paths. Compile stages one level down, under `.skf-stage` (88e175f8, PR #509), so its folder never collides with a `skills_output_folder` or `forge_data_folder` set to `_bmad-output`: SKF never reads a `.skf-` name as a skill (references/compile.md §1a). Only throw-away shallow git clones use `{system_temp}/skf-ephemeral-{skill-name}-{timestamp}/` (references/source-resolution-protocols.md and references/tier-degradation-rules.md; `grep -rn skf-ephemeral- src/` finds each site) and are deleted after extraction. A new step that stages files should keep to this split: the old step-03c-fetch-docs staged under `{system_temp}/skf-docs-{skill-name}/`, diverged from its sibling steps, and had to be realigned in PR #43 (05179fa9).
