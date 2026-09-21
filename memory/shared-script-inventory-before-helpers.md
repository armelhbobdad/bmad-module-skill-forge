---
created: "2026-05-01 12:53"
session: "284575a2-8a15-4e11-9fed-9260d1439119"
source: claude-mem
source_table: session_summaries
source_ids: [2411, 2412, 2442]
---

# Shared script inventory check before new helpers

`src/shared/scripts/` holds about 55 `skf-*.py` helpers and the only inventory is the one-row summary in `docs/architecture.md`, so quality reports can recommend building a script that already exists: a bmad-workflow-builder report on skf-quick-skill (finding QS-INT-03) proposed a new `skf-validate-quick-artifacts.py` when `skf-validate-output.py` already covered the body, snippet and metadata checks — the actual gap was the step hand-walking the checklist in prose instead of invoking the script (now `src/skf-quick-skill/references/write-and-validate.md` §5). Before writing a new helper from such a finding, `ls src/shared/scripts/` and grep the workflow's probe-order frontmatter for an existing script; the usual problem is integration debt, not missing functionality.
