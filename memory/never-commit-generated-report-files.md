---
created: "2026-03-17 18:36"
session: "f1dfa392-6b58-4d1a-881c-00a7f45a39fb"
source: claude-mem
source_table: observations
source_ids: [1500, 1501, 1502, 1504, 1505, 1506]
---

# Generated report files must never be committed

Generated validator and analyzer reports (for example the ten `validation-report-2026-03-17.md` files a BMB validation run dropped next to workflow sources) never go into a commit; a commit that bundled them with real fixes was reverted by the user: "I undo the commit. Why did you commit unneeded files like report files?" Stage fix files by explicit path (`git add <file> ...`, never `git add -A` or `git add .` after running validators or analyzers) and delete, or leave untracked, any report a tool wrote beside source. `.gitignore` covers `**/.analysis`, `**/.decision-log.md`, `_bmad-output` and `skills`, which is where BMB Analyze (`{target-skill-path}/.analysis/<timestamp>/`) and the module validator (`{bmad_builder_reports}/`) now write, but there is still no `validation-report-*.md` rule, so a report written inside `src/skf-*/` is kept out of a commit only by staging deliberately and checking `git status` before committing.
