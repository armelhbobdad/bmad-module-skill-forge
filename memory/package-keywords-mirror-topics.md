---
created: "2026-04-08 01:11"
session: "ac65f24f-90d0-4d0b-953c-a6070c7ddae8"
source: claude-mem
source_table: session_summaries
source_ids: [1345, 1346]
---

# package.json keywords mirror marketplace.json and GitHub topics

`package.json` `keywords` (16 entries: bmad, bmad-method, bmad-module, agent-skills, agentskills, agents, skills, skill-forge, compilation, forge, ast-grep, qmd, cocoindex, cocoindex-code, provenance, code-analysis), `.claude-plugin/marketplace.json` `keywords`, and the GitHub repository topics (`gh repo view --json repositoryTopics`) are kept as the same list. No test, validator or CI step compares them and CONTRIBUTING.md does not mention the rule, so a change to one must be applied by hand to the other two — the GitHub topics via `gh repo edit --add-topic` / `--remove-topic`.
