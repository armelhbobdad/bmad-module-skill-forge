---
created: "2026-04-09 12:35"
session: "c1c818a3-d210-4820-87e4-c747e698faa9"
source: claude-mem
source_table: observations
source_ids: [4980, 4981, 4986, 4993]
---

# Object-bearing trigger phrases in skf SKILL.md descriptions

Every `src/skf-*/SKILL.md` `description` ends in a `Use when the user requests to "..."` clause, and each quoted trigger phrase must carry its object — `"test a skill"`, `"create a skill"`, `"verify skill completeness"` — never a bare verb. A bare `"test"` or `"create"` fires the skill on unrelated requests such as "test the code" or "create a file"; the 2026-04-09 module quality scan flagged seven skills for this, the user said "fix them all", and skf-test-skill went from `"test" or "verify a skill"` to `"test a skill" or "verify skill completeness"` (commit 3f68b8f6). Nothing enforces it: `tools/validate-skills.js` SKILL-06 only checks that "Use when"/"Use if" is present and CONTRIBUTING.md:102 says the same. Three descriptions still carry a bare verb (skf-drop-skill `"drop"`, skf-export-skill `"export"`, skf-setup `"set up"`) — do not copy them as precedent when adding or editing a description.
