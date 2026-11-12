---
created: "2026-10-09 12:21"
session: "060dd6d3-2607-49df-93d3-74db880c67b5"
---

# npm run quality before each commit

The maintainer's rule for fix batches: "Run npm run quality before each commit (the pre-commit hook runs the full suite, about 20 minutes on this machine)", the `docs(changes): link this pull request's fragments to #N` follow-up included, not only before a push as `CONTRIBUTING.md` line 156 asks. `quality` runs the same steps as `npm test` plus `docs:validate-drift`, with the lints first, so it fails fast where `npm test` lints only after `test:python`. The drift check needs the oh-my-skills clone (`oh_my_skills_path: "../oh-my-skills"` in `docs/_data/pinned.yaml`, or `OMS=~/Projects/OSS/oh-my-skills` from a worktree elsewhere), and neither `.husky/pre-commit`, which runs `npm test`, nor CI runs it. In a chain script, capture the real status (`npm run quality > log 2>&1; echo "quality exit=$?" >> log`), commit only on 0, and run the pair in the background.
