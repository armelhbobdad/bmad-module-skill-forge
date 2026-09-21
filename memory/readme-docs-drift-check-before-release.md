---
created: "2026-05-03 00:55"
session: "ff53265a-3f96-4866-91b8-8639185c52eb"
source: claude-mem
source_table: observations
source_ids: [8529, 8530, 8531, 8532]
---

# README/docs drift check before cutting a release

Before dispatching release.yaml, compare what shipped with the user-facing docs: `git log --oneline v<last>..HEAD` next to `git diff v<last>..HEAD --name-only -- README.md docs/`; a long first list with an empty second means README.md and docs/ are behind and must be updated for the release. At the v1.4.0 cut, 104 commits since v1.3.0 (seven new src/shared/scripts, headless `--preset`/`--from-flat`, the exit-code and result-envelope contract) had landed with zero README/docs changes, and the `/skf-brief-skill` headless block in docs/workflows.md had to be written at release time. docs/_internal/RELEASING.md `## Cutting a Release` lists only the CHANGELOG `[Unreleased]` reconciliation and the bot-branch cleanup as per-cut steps, and tools/validate-docs-drift.js only checks pinned versions and SHAs, so nothing automated catches this. User: "I want to publish the next release. Check if we need to update the @README.md or @docs/ according to everything new after the last release."
