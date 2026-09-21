---
created: "2026-04-09 12:31"
session: "c1c818a3-d210-4820-87e4-c747e698faa9"
source: claude-mem
source_table: observations
source_ids: [4971, 4974, 4991, 4992]
---

# bmad-workflow-builder prepass false missing-stage criticals on the references/ layout

The locally installed, untracked `.claude/skills/bmad-workflow-builder/scripts/prepass-workflow-integrity.py` (bmad-builder v2.1.0; the upstream fix PR bmad-code-org/bmad-builder#82 was closed unmerged on 2026-06-22) only recognises stage files as root-level `NN-slug.md` and collects SKILL.md references with the unanchored regex `(?:prompts/)?(\d+-[^\s)`]+.md)`. On SKF's `references/`layout that produces 11 critical`Referenced stage file does not exist: 01-setup.md`…`11-maintenance.md`findings for`src/skf-campaign`(the`references/step-`prefix is stripped and nothing exists at the skill root) and zero findings — no stage, config-header or progression checks at all — for the other 15 skills whose reference files are unnumbered. Every such critical is a scanner artefact, not a repo defect: confirm with`ls src/skf-campaign/references/step-*.md`and do not rename, move or renumber files to appease it. A local patch of the scanner (a`discover_step_files()`walker over the step subdirectory,`group(0)`instead of`group(1)`) once cleared ~85 bogus criticals across the module, but any bmb reinstall restores the stock script and the wall of criticals returns.
