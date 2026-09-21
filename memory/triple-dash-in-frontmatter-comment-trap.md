---
created: "2026-04-13 17:14"
session: "a5591f15-f074-4f5f-b70e-8260eba1d5ef"
source: claude-mem
source_table: observations
source_ids: [6120, 6121, 6125]
---

# --- inside frontmatter comments breaks workflow-state tests

`test/test-workflow-state.js` extracts template frontmatter with `vsTemplate.split('---')[1]` (line 64), and `test/test-skf-campaign-stepfiles.py` closes frontmatter with `text.index("---", 3)` (lines 42, 87), so any `---` sequence inside the frontmatter block — including in a YAML comment — truncates the parsed field list. A comment line `# --- Producer-local bookkeeping (not part of the shared consumer contract) ---` in `src/skf-verify-stack/assets/feasibility-report-template.md` made 9 'VS State File Consistency' tests fail with `Missing from feasibility-report-template.md` and blocked the husky pre-commit hook; the comment now ends with a colon instead. Never write `---` inside the frontmatter of a step, template or asset file, or switch the extractor to match a line that is exactly `---` the way `test/test-skf-chain-reachability.py` does (`^---\n(.*?)\n---\n`).
