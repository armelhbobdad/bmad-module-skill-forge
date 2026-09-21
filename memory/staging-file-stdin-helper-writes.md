---
created: "2026-05-23 20:24"
session: "9372a162-5005-4c2a-9b02-ca3fbdf889bb"
source: claude-mem
source_table: observations
source_ids: [11314, 11315, 11321]
---

# Staging-file stdin for helper write commands

Generated content must never be inlined into a shell command in a step file: `--content "{managed_section_inner}"` or `echo "{...}" |` lets bash run command substitution on backticks and expand `$…`, silently corrupting the written bytes, and the helper's byte-identity verify still reports success because it compares against the already-corrupted string. No quoting style is safe (snippets also contain single quotes), so write the content to a staging file such as `{target-file}.skf-content` with the file-write tool and feed it by stdin redirection, e.g. `python3 {rebuildManagedSectionsHelper} {target-file} replace < "{target-file}.skf-content"`; both `src/shared/scripts/skf-atomic-write.py` and `skf-rebuild-managed-sections.py` read stdin whenever `--content` is absent. The rule is written only in `src/skf-export-skill/references/update-context.md` ("Stage content via a shell-safe channel"), while `src/skf-rename-skill/references/execute.md:278` and `src/skf-drop-skill/references/execute.md:159` still use `replace --content "{new_managed_section_text}"`, the exact pattern it forbids.
