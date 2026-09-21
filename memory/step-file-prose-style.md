---
created: "2026-04-08 18:47"
session: "22de972c-e2c4-42f6-8273-847aae2f80d7"
source: claude-mem
source_table: observations
source_ids: [4763, 4764, 4818, 7579]
---

# Step-file prose style: universal rules once in SKILL.md

Every `src/skf-*/SKILL.md` has a `## Workflow Rules` section (15 skills, e.g. `src/skf-quick-skill/SKILL.md:24`) that states the universal rules once — never fabricate, load one step file at a time, speak `{communication_language}`, the cancel-line affordance, headless auto-proceed — and each step file under `references/` carries only a short `## Rules` list of two to four step-specific imperatives (about 100 files, e.g. `src/skf-quick-skill/references/compile.md:17`). The `MANDATORY EXECUTION RULES` / `Universal Rules` / `Role Reinforcement` / `EXECUTION PROTOCOLS` / `CONTEXT BOUNDARIES` / `SYSTEM SUCCESS/FAILURE METRICS` blocks that BMAD-style step templates repeat in every step (about 45 lines and roughly 40% of a step's tokens) were stripped from all skills in April 2026 after the quality scans, together with emoji and FORBIDDEN/CRITICAL/NEVER phrasing; `grep -rl FORBIDDEN src` is 0 files today. Do not paste those blocks back when scaffolding a step from `bmad-workflow-builder` output, and do not add `Menu Handling Logic` headers to steps that have no menu — the scans flag both as template residue. The one deliberate survivor is the shared terminal step `src/shared/health-check.md:21`, whose anti-hallucination block is intentional. CONTRIBUTING.md records only the emoji ban (line 135), not the rest of this convention.
