---
created: "2026-05-15 13:34"
session: "aa307bf9-20a5-4395-aa9d-821b8dc28003"
source: claude-mem
source_table: observations
source_ids: [9484, 9498, 9499, 9502]
---

# Prose refers to stages as 'step N', never 'step-NN'

Because stage filenames carry no numeric prefix, prose, SKILL.md tables, JSON schema `description` fields and Python docstrings refer to a stage as `step 4` or `step 1b` — space-separated, no leading zero — matching the `#` column of that skill's Stages table, never `step-04` or a filename. Commit 468349ff (2026-05-15) normalised 548 occurrences across 144 files; at v2.1.0 the tree has ~960 `step N` references, with a few `step-NN` strays left in Python docstrings (`src/skf-test-skill/scripts/aggregate-coherence.py`, `compute-score.py`, `src/shared/scripts/skf-update-active-symlink.py`) and in a `workflow_warnings[]` `step:` value in `src/skf-create-stack-skill/references/init.md`. skf-campaign is the exception: its stage files are `references/step-NN-name.md`, so filename references there keep the hyphenated form. Nothing lints this, so write the space-separated form deliberately in any new step prose, docstring or schema description.
