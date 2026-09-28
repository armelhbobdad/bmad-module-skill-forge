---
created: "2026-05-22 11:55"
session: "4743dabc-fd96-4181-a146-86a715b1dbfe"
source: claude-mem
source_table: observations
source_ids: [10892, 10905, 10917, 10941]
---

# skf-rebuild-managed-sections.py adds its own SKF markers

`src/shared/scripts/skf-rebuild-managed-sections.py` `cmd_replace` and `cmd_insert` write their own fresh `<!-- SKF:BEGIN updated:<date> -->` / `<!-- SKF:END -->` markers around the text they receive, so they take only the body between the markers; before the helper refused it, passing a marker-bearing block (the template in `skf-export-skill/assets/managed-section-format.md`, which says "Replace everything between markers (inclusive)") nested a second SKF:BEGIN/SKF:END pair in CLAUDE.md/AGENTS.md — this was hit in a real export run. `skf-export-skill/references/update-context.md` §5 therefore splits `{managed_section_inner}` (for `insert`/`replace`) from `{managed_section_full}` (only for the Case 1 atomic create and the preview). Commit c2579385 closed the trap in the last two callers, skf-drop-skill `references/execute.md` §3 and skf-rename-skill `references/execute.md` §7, which had fed the marker-bearing template as `{new_managed_section_text}` to `replace --content` and now build `{managed_section_inner}` only. The same commit made the helper refuse such input and states the contract in its module docstring: `_marker_in_body_error` rejects content matching `MARKER_IN_BODY_PATTERN` (`<!--\s*SKF:(?:BEGIN|END)\b`) with exit 1 and leaves the file unchanged, while a prose mention of the marker names without `<!--` still passes; `test/test-skf-rebuild-managed-sections.py` pins the refusal and the callers (`TestBodyOnlyContent`, `TestCallersPassTheBody`). A caller that gets exit 1 with "content holds an SKF marker" is passing the whole section: strip the two marker lines rather than loosening the check.
