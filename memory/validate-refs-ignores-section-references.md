---
created: "2026-05-26 16:49"
session: "cf115121-04a4-4c4b-9c98-7c559e303f01"
source: claude-mem
source_table: observations
source_ids: [13415, 13416]
---

# validate:refs does not check §N section references

`npm run validate:refs` (tools/validate-file-refs.js, run by `npm test` and `npm run quality`) resolves only file-path references — `{project-root}/_bmad/...` paths, `./`/`../` relative paths, `nextStepFile`-style step metadata, `*Data:` frontmatter keys and ``Load: `...` `` directives (see its header, lines 8-16). It has no notion of intra-document `§N` cross-references and no other validator in tools/ or test/ checks them, yet src/ carries over 1,200 `§N` references in step prose. When a story removed §6/§7 from src/skf-brief-skill/references/step-auto-brief.md, five "Emit error envelope per §7" lines survived and the whole `npm test` suite passed with 0 errors (204 files, 172 refs checked). After renumbering, deleting or inserting a `##`/`###` section in any step file, grep that file and the files that load it for `§` and re-read each target by hand — the gate will not catch a dangling one.
