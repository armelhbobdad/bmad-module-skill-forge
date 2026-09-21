---
created: "2026-05-01 19:28"
session: "284575a2-8a15-4e11-9fed-9260d1439119"
source: claude-mem
source_table: session_summaries
source_ids: [8173, 8220]
---

# Audit-driven fix batches: one PR per theme, one commit per finding

For fix batches driven by a quality report or audit, the user's standing brief is: "@CONTRIBUTING.md Organize the commits and the PRs the smartest way (e.g: one commit per finding if applicable). Review all the changes for any breaking changes, or missing impacts/bugs/regressions and ect... Use feature-dev:code-reviewer skill before to push any PR. Always wait until I merge the current PR before you continue with the next PR on top of the previous one to avoid multiples merge conflicts. DO NOT HALLUCINATE. Activate party mode and/or advanced elicitation only if it is necessary. Use subagents the best way to avoid to polute the main session." In practice: one PR per theme, one commit per finding referencing its finding id (e.g. "theme 5 finding 5.3"), a code-review pass before every push (`feature-dev:code-reviewer` is no longer installed; `/code-review` or `bmad-code-review` is the equivalent), subagents for the heavy work, and never start the next PR until the user says the current one is merged. `CONTRIBUTING.md` § Workflow for Changes covers branch naming, conventional-commit scopes and `Fixes #NNN` but none of this organization.
