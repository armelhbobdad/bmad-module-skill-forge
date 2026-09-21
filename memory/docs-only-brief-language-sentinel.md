---
created: "2026-06-04 16:00"
session: "e58f8523-4c6a-4a67-9908-4211ba413cd7"
source: claude-mem
source_table: observations
source_ids: [15149, 15151, 15158]
---

# Docs-only briefs use "documentation" as language

`src/shared/scripts/skf-write-skill-brief.py` `validate_context()` (lines 197-201) dies with `required field 'language' missing or not a non-empty string` when `language` is `""`, and `src/shared/scripts/schemas/skill-brief.v1.json:65` sets `minLength: 1` — so a docs-only brief has no natural language value yet cannot leave the field empty. The convention is the literal sentinel `"documentation"`, as in the flat payload at `src/skf-analyze-source/references/auto-docs-only.md:72`; the prose rule at `src/skf-brief-skill/assets/skill-brief-schema.md:215` ("`language` must be a recognized programming language") is enforced nowhere and does not apply to docs-only briefs. The original payload was a decorative JSON example with `"language": ""` that became a live `--from-flat` writer invocation and halted every docs-only auto-scope run until the sentinel was substituted (PR #440).
