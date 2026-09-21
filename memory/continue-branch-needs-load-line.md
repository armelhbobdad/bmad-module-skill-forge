---
created: "2026-03-26 09:54"
session: "3dd3e331-e889-4e24-bd99-554a5ca4d2fa"
source: claude-mem
source_table: observations
source_ids: [2526]
---

# Continue branch without the nextStepFile load line stalls silently

A step-file branch that is meant to proceed but omits the line `Load, read the full file and then execute {nextStepFile}` makes the workflow silently stop after printing its message — the agent has nothing to do next and the run looks hung. Review finding VS-C1 hit this in verify-stack's coverage step: the 0%-coverage `[C] Continue` branch printed 'Continuing with 0% coverage — results will be limited.' and stopped, while the `[X] Halt` branch and the non-0% auto-proceed path were correct (fixed in `src/skf-verify-stack/references/coverage.md:172-174`). Every branch that continues — each menu option and each headless auto-decision — needs its own explicit load-and-execute line. `test/test-skf-chain-reachability.py` only checks that `nextStepFile` resolves on disk, and `tools/validate-skills.js` checks frontmatter and filenames, so nothing mechanical catches a missing line.
