---
created: "2026-09-21 20:09"
session: "f71394da-c254-432d-8ee7-d91d9c8ba833"
---

# Stacked PR: retarget to main by hand, then delete the base branch

This repo does not auto-delete merged branches, so a PR opened with a feature branch as its base merges *into that branch* if the base PR lands first: on 2026-09-21 #478 (`memory/claude-mem-migration` → `chore/remove-entire`) merged into the chore branch a minute after #477 had merged into `main`, leaving `main` without the memory commits, and #479 re-opened the same branch against `main`. Deleting the merged base branch afterwards does not retarget either: on 2026-09-30, `git push origin --delete v3/w1-tooling` after #615 merged CLOSED the stacked #616, #617 and #618 (GitHub retargets only when the branch is deleted by the merge itself). The safe order is `gh pr edit <n> --base main` for each stacked PR, then a check that `gh pr list --base <branch> --state open` is empty, then the delete. If they closed anyway, push the branch back at the same commit (`git push origin <sha>:refs/heads/<branch>`), run `gh pr reopen <n>`, retarget, and only then delete it; the reopen re-runs CI.
