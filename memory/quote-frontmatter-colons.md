---
created: "2026-03-07 10:07"
session: "b5e86916-237e-41aa-bcb1-718090d7b510"
source: claude-mem
source_table: observations
source_ids: [580, 581]
---

# Unquoted colons in a frontmatter description break YAML parsing

Installing the module once failed with `Failed to parse workflow at .../_bmad/skf/workflows/audit-skill/workflow.md: Nested mappings are not allowed in compact mappings at line 2, column 14` because the frontmatter read `description: Drift detection. Forge tier: structural. Deep tier: full.` — YAML treats the second `: ` as a nested mapping. Any frontmatter scalar (above all `description`) that contains `: ` must be wrapped in double quotes. The repo's own `validate:skills` (`tools/validate-skills.js:85-95`) splits each line at the first colon without a YAML parser, so `npm test` passes while every real parser downstream — the skill loader that reads `SKILL.md`, and `src/shared/scripts/skf-validate-frontmatter.py`, which reports `Invalid YAML in frontmatter: ...` for generated skills — fails.
