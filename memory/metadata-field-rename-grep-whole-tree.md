---
created: "2026-03-13 02:47"
session: "0306101c-7128-438c-9e26-e94174c24274"
source: claude-mem
source_table: observations
source_ids: [962, 963, 965, 966]
---

# Metadata field renames must be grepped across the whole src tree

The issue #13 alignment of `metadata.json` field names edited only the six obvious template and step files and left 54 `forge_tier` and 75 `skill_name` hits plus stray `generated_at`/`created_date` across the rest of `src/` (templates, schemas, step files, report templates); the rename was only complete after a second pass driven by `grep -rn` over the whole tree. The trap has a second edge: the same names are correct in sibling artifacts and must not be replaced blindly — `provenance-map.json` keeps `skill_name` and `generated_at` (`src/skf-create-skill/assets/skill-sections.md` § provenance-map.json Structure, `src/skf-create-stack-skill/assets/provenance-map-schema.md`), `skill-brief.yaml` keeps `forge_tier` (`src/shared/scripts/skf-write-skill-brief.py`, `src/skf-brief-skill/references/write-brief.md`), and the `SKF_*_RESULT_JSON` envelopes keep `skill_name`. So a metadata rename is done per artifact: grep every old name across `src/`, decide for each hit which artifact it belongs to, and only then call it finished.
