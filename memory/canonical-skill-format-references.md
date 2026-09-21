---
created: "2026-03-02 21:58"
session: "5ffd8cab-468c-4883-8285-e3acbf77742c"
source: claude-mem
source_table: observations
source_ids: [451, 452, 458, 466]
---

# Canonical references for skill-format questions

For anything about the shape of a generated `SKILL.md` — frontmatter fields, body size limits, the `scripts/` / `references/` / `assets/` layout, progressive disclosure — the user designated two references: Anthropic's best-practices page, <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices>, and the agentskills.io specification together with its `skills-ref` Python validator (github.com/agentskills/agentskills, `skills-ref/src/skills_ref/validator.py`). The user's request: "can we also consider these ref @temp/Best-Practices-for-Creating-Agent-Skills.md (the full doc: <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices>) and @temp/agentskills.io/ ?". The local copies under `temp/` were never committed and no longer exist; the in-repo synthesis is `src/knowledge/agentskills-spec.md` (its source line names both), and `src/shared/scripts/skf-validate-frontmatter.py` mirrors the upstream validator. Neither the Anthropic URL nor the validator's upstream is linked anywhere else in the repo, so re-fetch these two sources before changing format or validation rules instead of reasoning from the synthesis alone.
