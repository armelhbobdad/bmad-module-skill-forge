---
created: "2026-03-28 00:56"
session: "72eb9a6f-636e-40d4-971f-273e074cafa4"
source: claude-mem
source_table: both
source_ids: [2786, 2942, 5215, 5237]
---

# Squash a fix sweep into one commit before opening the PR

After a review or bug-fix sweep produces a run of small fix commits on a feature branch, squash them into a single consolidated commit (message listing the resolved findings) before the branch is pushed and the PR to `main` is opened. User: "squash the recent 3 fix commits", "squash the 3 most recent fix commits.", "yes commit. We should end up with only one commit for docs, so use squash". Mechanics: `git reset --soft <base-sha>` (or `HEAD~N`), one new commit, then `git push --force-with-lease` when the branch is already on origin. It matters because PRs in this repo land as merge commits (see the `Merge pull request` history; `docs/_internal/RELEASING.md:22` allows merge/squash/rebase but merge is what is used), so every intermediate fix commit would otherwise end up on `main`. Offer the squash at the end of a fix sweep instead of pushing N fix commits.
