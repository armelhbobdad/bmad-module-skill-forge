---
created: "2026-05-02 23:23"
session: "97eacf6a-1b45-4fae-ae85-130d633737d7"
source: claude-mem
source_table: observations
source_ids: [8445, 8446]
---

# No /skf-help command exists

There is no `skf-help` skill: `ls src/` lists sixteen `skf-*` directories (skf-analyze-source through skf-verify-stack) and none is a help command; SKF's help surface is `/bmad-help` (only when BMad Method is installed, fed by `src/module-help.csv`) and `@Ferris`. A draft of the brief-skill welcome message once pointed at `/skf-help`; code review caught it and the text now points at `/skf-create-skill` and `/skf-export-skill` (src/skf-brief-skill/references/gather-intent.md). The `skf-*` naming pattern makes this an easy slip and no validator catches it — `tools/validate-file-refs.js` checks file paths, not slash commands — so check every `/skf-*` command named in user-facing prose against `ls src/` before committing.
