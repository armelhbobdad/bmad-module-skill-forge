---
created: "2026-04-25 00:27"
session: "07e394fc-8689-4ad9-95e8-90a9f20b5dcd"
source: claude-mem
source_table: observations
source_ids: [7304, 7305]
---

# docs:validate-drift runs only in npm run quality and needs the oh-my-skills sibling checkout

`npm run docs:validate-drift` (`tools/validate-docs-drift.js`) is the last step of `npm run quality` and nothing else runs it: `.github/workflows/quality.yaml` calls the scripts one by one without it, and `npm test` (run by `.husky/pre-commit` and `release.yaml`) omits it. Green CI therefore proves nothing about versions in docs/ drifting from oh-my-skills, so run it by hand before merging changes to docs/ or `docs/_data/pinned.yaml`. CONTRIBUTING.md ("The same steps run in .github/workflows/quality.yaml on every pull request") and the script header ("enforced here at CI/pre-commit time") still claim otherwise, while docs/verifying-a-skill.md and the `pinned.yaml` header say CI does not run it. It checks `skf_version` against `package.json` (release.yaml bumps `pinned.yaml` in the release commit), then reads `$OMS/skills/<name>/<version>/<name>/metadata.json` for oms-cognee, oms-cocoindex, oms-storybook-react-vite and oms-uitripled. The clone comes from `OMS`, else `oh_my_skills_path: "../oh-my-skills"` resolved against the running checkout (`path.resolve(SKF_ROOT, anchors.oh_my_skills_path)`), so every git worktree (such as `.claude/worktrees/<lane>`) fails with `DRIFT DETECTED:` and `CRITICAL: oh_my_skills_path does not resolve to a directory: ...`, exit 1, whatever the change. Export `OMS=$HOME/Projects/OSS/oh-my-skills` for any run outside the main checkout, put it in every lane agent's brief, and after such a failure rerun only the drift step.
