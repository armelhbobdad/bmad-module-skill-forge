---
created: "2026-06-03 18:19"
session: "ab575e86-8acf-4f61-85b2-5e9d5bed1496"
source: claude-mem
source_table: observations
source_ids: [14673, 14674, 14677]
---

# skf-campaign numbered step files are a deliberate exception

`src/skf-campaign/references/step-01-setup.md` … `step-11-maintenance.md` are the only numbered step files left under `src/`; every other skill switched to descriptive filenames in commit d7861786 (2026-05-15). The bmad-workflow-builder quality principles say stages get descriptive names, never numbered prefixes, and its architecture scanner reports the campaign files as a LOW finding. Here the numbers are load-bearing state, not a leftover: `campaign.current_stage` (0-indexed) maps to `step-NN` (1-indexed, see `src/skf-campaign/SKILL.md` "Stage numbering"), each step's `nextStepFile` chains to the next number, `references/step-resume.md` §3–§4 resolve a stage back to its file on resume, and `test/test-skf-campaign-stepfiles.py` globs `step-\d+-`. Accept the scanner finding rather than renaming the files. Note that CONTRIBUTING.md:102 still describes `step-NN-<slug>.md` as the general rule while `tools/validate-skills.js` only scans `steps-c/` or `steps/`, so neither document nor validator reflects the current split.
