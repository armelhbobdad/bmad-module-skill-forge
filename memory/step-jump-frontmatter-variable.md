---
created: "2026-02-27 13:11"
session: "f7c16d4f-fdb6-4264-ae63-0c398c21bced"
source: claude-mem
source_table: observations
source_ids: [388, 390]
---

# Non-sequential step jumps declared as frontmatter variables

A step file that jumps to a sibling step other than its `nextStepFile` declares that target as its own frontmatter variable and references it in the body as `{variableName}`, never as a literal filename and never as a second `nextStepFile`. The BMB workflow validator once failed update-skill's detect-changes step for naming `./step-07-report.md` literally at three lines of its no-change shortcut; the fix was a `noChangeReportFile` variable referenced as `{noChangeReportFile}`. Today that variable is `noChangeReportFile: 'report.md'` in `src/skf-update-skill/references/detect-changes.md:3`, used at lines 492-509, and the same pattern covers `componentExtractionStepFile`, `continueFile`, `ratifyTargetFile`, `rejectTargetFile` and `reviseStepFile` in other skills. The key must differ from `nextStepFile` because `test/test-skf-chain-reachability.py` (`_next_step`) reads a single `nextStepFile` per step file and walks that chain for reachability, so a second one would be ignored or replace the forward chain. `npm run validate:refs` (`tools/validate-file-refs.js`) only checks that referenced paths resolve, so a literal jump passes `npm run quality` unnoticed.
