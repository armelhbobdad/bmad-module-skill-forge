---
created: "2026-09-21 20:09"
session: "f71394da-c254-432d-8ee7-d91d9c8ba833"
---

# Stacked PR retargets to main only when its base branch is deleted

GitHub retargets a pull request to the default branch only when its base branch is deleted on merge; this repo does not auto-delete merged branches, so a PR opened with a feature branch as base merges *into that branch* if the base PR lands first. It happened on 2026-09-21: #478 (`memory/claude-mem-migration` → `chore/remove-entire`) merged into the chore branch a minute after #477 (`chore/remove-entire` → `main`) had merged, leaving `main` without the memory commits; #479 re-opened the same branch against `main`. When stacking here, either delete the base branch as part of merging the first PR, or retarget the stacked PR to `main` by hand (`gh pr edit <n> --base main`) before merging it.
