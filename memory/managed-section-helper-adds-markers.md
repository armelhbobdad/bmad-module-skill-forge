---
created: "2026-05-22 11:55"
session: "4743dabc-fd96-4181-a146-86a715b1dbfe"
source: claude-mem
source_table: observations
source_ids: [10892, 10905, 10917, 10941]
---

# skf-rebuild-managed-sections.py adds its own SKF markers

`src/shared/scripts/skf-rebuild-managed-sections.py` `cmd_replace` (line 194) and `cmd_insert` (line 239) wrap whatever `--content`/stdin text they receive in fresh `<!-- SKF:BEGIN updated:<date> -->` / `<!-- SKF:END -->` markers; the docstring does not say so. Passing a marker-bearing block (the template in `skf-export-skill/assets/managed-section-format.md`, whose §110 says "Replace everything between markers (inclusive)") produces duplicated SKF:BEGIN/SKF:END lines in CLAUDE.md/AGENTS.md — this was hit in a real export run. `skf-export-skill/references/update-context.md` §5 now splits `{managed_section_inner}` (for `insert`/`replace`) from `{managed_section_full}` (only for the Case 1 atomic create and the preview). `src/skf-drop-skill/references/execute.md` (~line 138-159) and `src/skf-rename-skill/references/execute.md` (~line 259-278) still assemble the marker-bearing template and feed it as `{new_managed_section_text}` to `replace --content`, so those two call sites still carry the double-wrap trap — pass inner text only, or fix them the way update-context.md was fixed.
