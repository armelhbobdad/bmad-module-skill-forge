---
created: "2026-03-14 18:34"
session: "399dba32-15e7-4ca7-b421-c491359347a7"
source: claude-mem
source_table: observations
source_ids: [1177, 1178]
---

# External tools invoked by workflows are listed in README and docs

When a workflow is wired to a new external tool, the tool is listed everywhere the existing ones already are: the `## Acknowledgements` table in README.md (rows for GitHub CLI, ast-grep, cocoindex-code, QMD, skill-check, Snyk Agent Scan, tessl), the `### 7 Tools` table under `## Tool Ecosystem` in docs/architecture.md, and the capability-tier table in docs/skill-model.md. A proposal to wire tessl into the workflows without documenting it was reversed by the user: "But we listed `skill-check` tool in README (we also have the Acknowledgements section) and docs. why we should not add tessl?" CONTRIBUTING.md names 'Ecosystem integrations' as a contribution type but records no such listing rule, so it is easy to skip.
