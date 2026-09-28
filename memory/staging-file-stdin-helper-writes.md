---
created: "2026-05-23 20:24"
session: "9372a162-5005-4c2a-9b02-ca3fbdf889bb"
source: claude-mem
source_table: observations
source_ids: [11314, 11315, 11321]
---

# Staging-file stdin for helper write commands

Generated content must never be inlined into a shell command in a step file: `--content "{managed_section_inner}"` or `echo "{...}" |` lets bash run command substitution on backticks and expand `$…`, silently corrupting the written bytes, and the helper's byte-identity verify still reports success because it compares against the already-corrupted string. No quoting style is safe (snippets also contain single quotes), so write the content to a staging file such as `{context_file}.skf-content` with the file-write tool and feed it by stdin redirection, e.g. `python3 {rebuildManagedSectionsHelper} "{context_file}" replace < "{context_file}.skf-content"`; `skf-atomic-write.py write` takes its content only from stdin, and `skf-rebuild-managed-sections.py` reads stdin whenever `--content` is absent. The rule is written in `src/skf-export-skill/references/update-context.md` §9 ("Stage content via a shell-safe channel") and, since commit c2579385, in skf-drop-skill `references/execute.md` §3 and skf-rename-skill `references/execute.md` §7, which replaced their `replace --content "{new_managed_section_text}"` calls with a staged `{managed_section_inner}` (no trailing newline, staging file deleted once the helper returns). The same commit made `skf-rebuild-managed-sections.py` decode stdin itself (`sys.stdin.buffer.read().decode("utf-8")`), because `sys.stdin` decodes a pipe or redirect with the locale's code page (cp1252 on Windows) and turns the em dash on each skill snippet's `|IMPORTANT:` line into mojibake that the byte-identity check accepts. Any new step that hands generated text to a helper must use the same staging-file-plus-redirect shape.
