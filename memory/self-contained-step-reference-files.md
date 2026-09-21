---
created: "2026-05-16 01:07"
session: "368f6026-a320-4e3c-ab70-9bedb28ba90c"
source: claude-mem
source_table: observations
source_ids: [9947, 9949]
---

# Self-contained step reference files

Every workflow step file under src/skf-*/references/ (121 files carrying `nextStepFile:`, including src/skf-create-skill/references/sub/*.md and carve-outs such as src/skf-quick-skill/references/batch-mode.md) opens with its own frontmatter and the `<!-- Config: communicate in {communication_language}. -->` header even though SKILL.md already establishes them. The duplication is deliberate: context compaction can drop SKILL.md mid-flow, so each step file must work when it is the only thing loaded. No validator enforces the header (tools/validate-skills.js checks STEP-01, STEP-06 and STEP-07 only), so a dedup or 'reduce boilerplate' pass can strip it without any test failing. Do not strip it.
