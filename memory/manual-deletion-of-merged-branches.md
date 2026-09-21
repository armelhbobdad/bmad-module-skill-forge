---
created: "2026-05-24 23:58"
session: "0449feb1-ce21-4cf6-9958-2e1d69f376a3"
source: claude-mem
source_table: observations
source_ids: [12137, 14939, 14940]
---

# Manual deletion of merged PR branches

`gh api repos/armelhbobdad/bmad-module-skill-forge --jq .delete_branch_on_merge` returns `false`, so after a PR merges both the local branch and `origin/<branch>` stay behind (seen after PRs #397, #398 and #439). The user asked for the cleanup twice: "delete local and remote branches" and "merged. You should also delete the remote branch (+local) you just created." After every merge: `git switch main && git pull`, `git branch -d <branch>`, `git push origin --delete <branch>`, `git fetch --prune`. The only branch-deletion note in the repo, docs/_internal/RELEASING.md:210-212, covers the release bot's `release/bot/vX.Y.Z-<run_id>` branch after an admin-bypass merge; CONTRIBUTING.md says nothing about ordinary `fix/*`, `feat/*` or `docs/*` branches.
