---
created: "2026-04-08 18:46"
session: "22de972c-e2c4-42f6-8273-847aae2f80d7"
source: claude-mem
source_table: observations
source_ids: [4762, 4764]
---

# 'Never fabricate' wording replaces the BMB no-user-input rule

SKF SKILL.md Workflow Rules state the zero-hallucination rule as `Never fabricate content — all data must come from source extraction or user input` (`src/skf-quick-skill/SKILL.md:28`; `src/skf-audit-skill/SKILL.md:29` uses the same shape with 'findings'). The BMB step-file boilerplate `NEVER generate content without user input` — still present in a locally installed BMad Method (`.claude/skills/bmad-*/steps/*.md`, untracked) but nowhere under `src/` — was deliberately dropped because SKF steps auto-proceed and emit compiled output with no user turn, so that sentence literally contradicts them. When scaffolding a new `skf-*` skill from BMB templates or the workflow builder, keep the 'never fabricate' wording rather than the BMB sentence.
