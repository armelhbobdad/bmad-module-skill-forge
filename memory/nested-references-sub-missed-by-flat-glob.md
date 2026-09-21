---
created: "2026-05-16 04:40"
session: "ffc814aa-7ebd-4d13-a41d-9267584b3862"
source: claude-mem
source_table: observations
source_ids: [10042, 10047]
---

# Nested references/sub/ step files missed by flat glob

src/skf-create-skill/references/sub/ (ccc-discover.md, fetch-docs.md, fetch-temporal.md) is the only nested references directory in src/, and the skill layout in CONTRIBUTING.md does not mention it. A bulk edit driven by the flat glob `src/*/references/*.md` silently skipped those three files during the `**CRITICAL:** Follow this sequence` banner removal; the fix was to match every `*.md` with `references` anywhere in its path (e.g. `find src -path '*/references/*' -name '*.md'`) and to verify with a grep for the removed text across the whole src/ tree, expecting 0. Use that shape for any bulk step-file edit, and remember that files in sub/ navigate with `../` (nextStepFile: '../extract.md') while parents descend with `sub/`.
