---
created: "2026-04-27 12:14"
session: "4413807b-d437-4757-bb96-ea6cb8c785dd"
source: claude-mem
source_table: observations
source_ids: [7716, 7717, 9629, 9633]
---

# Language config header in workflow stage files

Every workflow stage file under `src/skf-*/references/` (the prompts chained via frontmatter `nextStepFile`) carries an HTML-comment directive immediately after the frontmatter close and before the H1: `<!-- Config: communicate in {communication_language}. -->`; skf-setup's variants also say which user-visible text renders in `{document_output_language}`, and `src/skf-setup/references/report.md:14` notes that JSON result envelopes such as `SKF_SETUP_RESULT_JSON` stay English as machine contracts. Static reference docs (`tier-rules.md`, `extraction-patterns.md`, `*-schema.md`, `exit-codes.md`) do not carry it. The header exists because SKILL.md's "Always communicate in `{communication_language}`" rule is lost once the context is compacted away from SKILL.md, so a stage file loaded on its own must restate it. Nothing in `npm run quality` enforces this; only the local, gitignored bmad-workflow-builder scanner (`.claude/skills/bmad-workflow-builder/scripts/prepass-workflow-integrity.py`) flags a stage file without it as medium 'No config header with language variables found'. When adding or carving a stage file, insert the header; the insertion is idempotent.
