---
created: "2026-03-17 23:16"
session: "e95bcf48-b3ad-46c7-9490-7389934ffffd"
source: claude-mem
source_table: observations
source_ids: [1664, 1670]
---

# Extraction protocol prose is mirrored in update-skill re-extract

`src/skf-update-skill/references/re-extract.md` declares its own `extractionPatternsData` / `extractionPatternsTracingData` keys pointing at `skf-create-skill/references/extraction-patterns.md` and `extraction-patterns-tracing.md` — the same two data files `src/skf-create-skill/references/extract.md` loads via skill-relative `references/...` keys — and it repeats the step-level extraction protocol in its own prose: the "Re-export tracing (Forge/Deep only)" paragraph lives at extract.md:196 and again at re-extract.md:271. A change to the shared data file reaches both workflows, but a protocol change written into extract.md's steps does not: the #46 re-export-tracing change shipped only in create-skill and code review caught update-skill still missing it. `src/skf-update-skill/SKILL.md` §Cross-skill data coupling names the shared files, but nothing on the create-skill side points back, so when changing extraction steps in extract.md, mirror the change in re-extract.md (and check `skf-quick-skill`, which does its own surface-level extraction).
