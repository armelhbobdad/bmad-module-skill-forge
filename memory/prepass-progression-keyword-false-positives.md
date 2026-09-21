---
created: "2026-04-27 12:14"
session: "4413807b-d437-4757-bb96-ea6cb8c785dd"
source: claude-mem
source_table: observations
source_ids: [7716, 7717, 8088, 8089, 8258, 8259]
---

# prepass-workflow-integrity progression check is a literal keyword list

`check_prompt_basics()` in bmad-workflow-builder's untracked `.claude/skills/bmad-workflow-builder/scripts/prepass-workflow-integrity.py` flags a stage file `medium` at line 1 unless it contains `{communication_language}` or `{document_output_language}`, `high` (`No progression condition keywords found`, anchored at the last line) unless its lowercased text contains one of `progress`, `advance`, `move to`, `next stage`, `when complete`, `proceed to`, `transition`, `completion criteria`, and `low` for `please` (except `please note`), `when ready`, `you should`, `handle appropriately`. SKF's chain idiom ("ONLY WHEN … load `{nextStepFile}`, read it fully, then execute it") and genuinely terminal `references/health-check.md` steps contain none of those words, so they draw false `high` progression findings. Treat them as scanner noise: never invent a next step or rewrite behaviour to satisfy the regex; if a finding must be cleared, add the vocabulary (e.g. `proceed to` in the chain sentence) and nothing else. The `## Completion criteria` section added to skf-brief-skill's terminal step in May 2026 solely for this scanner was removed again in July (commit f4a2e52f) as redundant, and the stock scanner only inspects root-level `NN-*.md` files, so on the current `references/` layout these checks fire only if the scanner has been patched to walk `references/`.
