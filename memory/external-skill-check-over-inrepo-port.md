---
created: "2026-03-12 13:45"
session: "8cf2aaa1-21f3-4d9f-8089-0f9da2ea0019"
source: claude-mem
source_table: observations
source_ids: [776, 785, 788, 790, 792, 793]
---

# External skill-check chosen over an in-repo validator port

Full SKILL.md validation in SKF is delegated to the external `npx skill-check` (github.com/thedaviddias/skill-check), invoked as `npx skill-check check {skillDir} --format json --no-security-scan` in `src/skf-test-skill/references/external-validators.md`; the Python `skills-ref` from the agentskills spec was rejected because most users do not have it installed. A Node port of skills-ref was built in `tools/skill-check/` and deleted the same day; the user asked for it: "It is more mature implementation rather than our built-in tool. May be we should take the full advantage of this tool instead on relying on our internal and poor tool. what do you think? May be we should completely drop the commit related to adding ot the built-in tool". The port had 5 rules vs skill-check's 22 and lacked the 0-100 quality score, `--fix`, `split-body`, security scan and JSON/SARIF output; its `skill-check` bin name also collided on npm. Those commits are not on `main`, so git history does not show this was tried. The only in-repo validator is `src/shared/scripts/skf-validate-frontmatter.py`, a deterministic frontmatter pre-check aligned with skills-ref — do not grow it into a second full validator.
