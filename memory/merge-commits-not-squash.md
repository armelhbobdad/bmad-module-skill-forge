---
created: "2026-05-18 17:42"
session: "900827df-c0f7-4954-b899-977f414b6435"
source: claude-mem
source_table: both
source_ids: [2874, 10101]
---

# Merge commits, not squash, for PRs into main

PRs into `main` are merged with "Create a merge commit": every merge on main is a `Merge pull request #N` commit. The original reason is gone since #578: release.yaml no longer builds the CHANGELOG from the `feat:`/`fix:` subjects that reach main (where a squash dropped all but one entry), because notes now come from the change fragments in `changes/*.yaml` whatever the merge style. Two reasons remain. A PR may carry a separate `chore(memory):` commit, since memory changes never share a commit with code, and a squash would fold it into the code commit. And release.yaml's "Auto-merge bot PR" step merges the bot release PR with `--merge`: when main moved during the run, "Create and push tag" puts the tag on the release commit, which main reaches only through the merge commit's second parent, so a squash or rebase merge of the bot PR makes the run stop before publishing. Branch protection still allows merge, squash and rebase alike (the ruleset table in docs/_internal/RELEASING.md), so nothing enforces this for ordinary PRs.
