---
created: "2026-03-14 18:22"
session: "399dba32-15e7-4ca7-b421-c491359347a7"
source: claude-mem
source_table: session_summaries
source_ids: [427, 428, 429, 430]
---

# npx tessl invocations need -y inside workflow steps

Every tessl call in a step file carries `-y`: `timeout 120s npx --no-install -y tessl skill review {skillDir}` in `src/skf-test-skill/references/external-validators.md` (lines 85, 101) and `timeout 120s npx -y tessl skill review <staging-skill-dir>` in `src/skf-create-skill/references/validate.md` (lines 205, 214). Without `-y`, npx stops on its package-install confirmation prompt when the package is not already cached, and the workflow step hangs with no error text — the only symptom is a step that never returns. Nothing in the step files says why the flag is there; the rationale exists only in commit 9bda9034 ('Both workflows use npx -y to auto-accept install prompts'). Keep `-y` on any npx invocation of a package that may not be installed, and pair it with the `--no-install` probe plus `timeout` pattern external-validators.md uses so a cold download can never block a step either.
