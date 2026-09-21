---
created: "2026-05-26 19:38"
session: "0f584fcd-01f3-407f-b8f4-d029686878d0"
source: claude-mem
source_table: observations
source_ids: [13550, 13621, 13708, 13711]
---

# Checklist for inserting a step into an skf workflow chain

Inserting a step into an `skf-*` chain is never a single-file change: the new `references/<step>.md` (frontmatter `nextStepFile`, STEP GOAL heading, section-prefixed sections), the predecessor's `nextStepFile`, a new row in the SKILL.md Stages table (plus the exit-codes table and `halt_reason` enum when the step can halt), a `test/test-skf-<step>.py` registered in package.json `test:python`, and the predecessor's existing chain test — `test/test-skf-step-doc-sources.py` failed with `'validate.md' == 'step-auto-shard.md'` after step-auto-shard was inserted between doc-sources and validate. `src/skf-test-skill/references/report.md` §5 additionally hardcodes the canonical `stepsCompleted` chain (`init, detect-mode, coverage-check, coherence-check, external-validators, hard-gate, score, report`) and `templates/test-report-template.md` carries an anchor-mapping comment, so a test-skill step wired via `nextStepFile` but not appended there makes the report step HALT with 'step completeness violation'; `skf-create-skill`'s report.md has no such list. Grep the old successor's name and the new step's name across the skill directory and `test/` before calling the insertion done.
