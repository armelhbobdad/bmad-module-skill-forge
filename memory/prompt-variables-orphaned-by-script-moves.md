---
created: "2026-05-15 14:20"
session: "aa307bf9-20a5-4395-aa9d-821b8dc28003"
source: claude-mem
source_table: both
source_ids: [9540, 9541, 9543]
---

# Prompt variables orphaned by moving logic into scripts

Commit `c0a9e9cd` moved the `qmd collection list` call out of the skf-setup prompt into `src/shared/scripts/skf-qmd-classify-collections.py`, but `src/skf-setup/references/auto-index.md` §4 still passed `--qmd-live-names "{live_collections}"` to `skf-forge-tier-rw.py clean-stale` and nothing set `{live_collections}` any more — the LLM had no valid value and the failure showed only in a quality scan, never in tests. The fix added `live_names` (sorted, ALL live collections, forge-owned and foreign) to the classifier's JSON and §2 now sets `{live_collections}` from it ("the script owns the raw set, the prompt only forwards it"); rebuilding the set prompt-side as healthy ∪ orphaned would drop foreign collections and undo the PR #244 protection. When moving a computation from a reference prompt into a helper script, grep the prompt for every `{variable}` it still references and confirm each is still populated from the script's output.
