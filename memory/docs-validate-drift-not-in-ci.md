---
created: "2026-04-25 00:27"
session: "07e394fc-8689-4ad9-95e8-90a9f20b5dcd"
source: claude-mem
source_table: observations
source_ids: [7304, 7305]
---

# docs:validate-drift runs only in npm run quality and needs the oh-my-skills sibling checkout

`npm run docs:validate-drift` (`tools/validate-docs-drift.js`) is the last step of `npm run quality` in `package.json`, but nothing else runs it: `.github/workflows/quality.yaml` invokes the validate/test scripts one by one and never calls `npm run quality` or the drift check, and `npm test` (what `.husky/pre-commit` and `release.yaml` run) omits it too. Three places claim otherwise — CONTRIBUTING.md ("The same steps run in .github/workflows/quality.yaml on every pull request"), docs/verifying-a-skill.md ("the CI fails before the docs get merged") and the script's own header ("enforced here at CI/pre-commit time"). The script checks `docs/_data/pinned.yaml` `skf_version` against `package.json` (release.yaml keeps that half green by bumping `pinned.yaml` in the release commit) and then opens `$OMS/skills/<name>/<version>/<name>/metadata.json` for each pinned skill (oms-cognee, oms-cocoindex, oms-storybook-react-vite, oms-uitripled) in a machine-local oh-my-skills clone resolved from `pinned.yaml` `oh_my_skills_path: "../oh-my-skills"` or the `OMS` env var; without that clone it prints `DRIFT DETECTED:` / `CRITICAL: oh_my_skills_path does not resolve to a directory: ...` and exits 1 for reasons unrelated to the change under test, which is likely why CI skips it. Green CI therefore proves nothing about pinned versions or version strings in docs/ drifting from oh-my-skills; run `npm run docs:validate-drift` by hand (with the sibling clone or `OMS=/path`) before merging anything that touches docs/ or pinned versions.
