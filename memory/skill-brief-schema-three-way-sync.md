---
created: "2026-03-18 21:28"
session: "d40284ec-234d-4a3e-bacb-2d72ebd53a47"
source: claude-mem
source_table: observations
source_ids: [1808, 4284, 11275, 11281]
---

# Three-way skill-brief schema sync

The skill-brief schema is defined in three places that are not identical copies and must all change together when a brief field is added or renamed: the validator schema `src/shared/scripts/schemas/skill-brief.v1.json` (consumed by `skf-validate-brief-schema.py` and `skf-write-skill-brief.py`), and two prose mirrors — `src/skf-brief-skill/assets/skill-brief-schema.md` (220 lines, field tables plus the YAML template and Version Detection section) and `src/skf-analyze-source/assets/skill-brief-schema.md` (135 lines, analyze-source's output contract, field definitions only). `target_version` and then `target_ref` were each added to one place first and the mirrors were caught missing afterwards. No test enforces the sync: `test/test-installation-components.js` only checks that the two `.md` assets exist, so grep all three for the field name before closing a brief-schema change.
