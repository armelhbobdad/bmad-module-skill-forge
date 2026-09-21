---
created: "2026-05-18 17:42"
session: "900827df-c0f7-4954-b899-977f414b6435"
source: claude-mem
source_table: both
source_ids: [2874, 10101]
---

# Merge commits, not squash, for PRs into main

PRs into `main` are merged with "Create a merge commit" (every merge on main is a `Merge pull request #N` commit) because `.github/workflows/release.yaml:161-163` generates the CHANGELOG entry with `npx conventional-changelog-cli -p conventionalcommits -i CHANGELOG.md -s`, which reads the leaf `feat:`/`fix:` commits that reach main. Squash-merging collapses a branch (PR #341 carried 38 conventional commits) into a single subject, so all but one entry vanish from the next release's block; `chore:` and `test:` subjects never produce an entry either way (`docs/_internal/RELEASING.md:208`). Nothing enforces this: branch protection and the repository settings allow merge, squash and rebase alike (RELEASING.md:22), and RELEASING.md:501 uses `gh pr merge --squash` only for a single-commit revert PR. The merge itself never bumps `package.json`; the release workflow does that afterwards on the bot branch.
