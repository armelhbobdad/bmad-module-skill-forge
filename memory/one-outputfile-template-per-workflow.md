---
created: "2026-04-04 19:57"
session: "6fa45512-d599-4dbb-85f0-8a269d8b745e"
source: claude-mem
source_table: observations
source_ids: [4331, 4332, 4333]
---

# One outputFile template across every step of a workflow

In the audit-skill workflow, `init.md` once wrote the drift report to `{forge_version}/drift-report-{timestamp}.md` while the next five steps wrote to `{forge_data_folder}/{skill_name}/drift-report-{timestamp}.md` — one directory up, because `{forge_version}` resolves to `{forge_data_folder}/{skill-name}/{version}/` (src/knowledge/version-paths.md:35). Step 1 created the report and steps 2–6 "updated" a file that never existed, and nothing failed: LLM-executed step files do not error on a one-level-off path (introduced in commit 30c457c, fixed by aligning every step to `{forge_version}`). Today all of `src/skf-audit-skill/references/{init,re-index,structural-diff,semantic-diff,severity-classify,step-doc-drift,report}.md` carry the identical `outputFile`, but the only tests pinning such agreement are `test/test-skf-step-hard-gate.py` (the `{forge_version}` placeholder in one file) and `test/test-workflow-state.js` (refine-architecture `compile.md`/`report.md` must match). When adding or editing a step that writes a shared output, grep every sibling step's `outputFile` and make the template byte-identical — a path that is almost right is the silent failure mode of this codebase.
