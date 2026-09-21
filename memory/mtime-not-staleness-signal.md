---
created: "2026-03-28 15:46"
session: "b78c356b-1b4c-4527-9f01-7efe13cdaa12"
source: claude-mem
source_table: session_summaries
source_ids: [926, 927, 928, 929, 1052]
---

# File mtime is not a staleness signal for cached evidence reports

`src/skf-test-skill/references/external-validators.md` §1b decides whether a cached evidence report can be reused by comparing `git log -1 --format=%cI -- {skillDir}/SKILL.md` with the report's generation date, adding `git diff` / `git diff --cached` for uncommitted changes and `metadata.json.generation_date` as the non-git fallback. The first version (commit 6078d085, 2026-03-21) compared SKILL.md's last-modified timestamp instead and was replaced in 0ab7b583 (2026-03-28): a file's mtime is reset by every clone and checkout, so it says nothing about whether the content changed since the report was produced. Do not simplify the staleness check back to a `stat`/mtime comparison — git commit timestamps plus uncommitted-change detection are the signal.
