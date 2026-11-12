---
created: "2026-04-21 14:52"
session: "0bcaebd1-df5f-4b64-b72d-1795416d0356"
source: claude-mem
source_table: both
source_ids: [2069, 6994, 7008, 2110, 2128, 8287, 8288]
---

# Landing a green PR on main needs gh pr merge --admin

`main` is guarded by the GitHub ruleset `Default` (id 13855503): 1 approving review, `require_code_owner_review` (vacuous: there is no `.github/CODEOWNERS`), the required status checks listed in docs/\_internal/RELEASING.md (one per quality.yaml job), and one bypass actor, the Admin role in `pull_request` mode. There is no legacy branch protection, so `gh api repos/armelhbobdad/bmad-module-skill-forge/branches/main/protection` answers 404 `Branch not protected` even while `gh pr merge` on a fully green PR fails with `base branch policy prohibits the merge` and `gh pr view --json reviewDecision` stays `REVIEW_REQUIRED`. GitHub never lets an author approve their own PR, so on the maintainer's own PRs the practice (in the user's words, "I manually merge to main") is to wait for the checks and land with `gh pr merge --admin`, adding `--merge` to keep the branch's commits. A PR someone else opened needs no bypass: on Dependabot PR #772 (2026-11-01), `gh pr review 772 --approve` from the maintainer's account made it `APPROVED CLEAN` and `gh pr merge 772 --merge --delete-branch` landed it. `release.yaml`'s `Wait for PR approval or admin-bypass merge` step accepts an admin-bypass merge of the bot release PR as approval, and docs/\_internal/RELEASING.md documents that path for release cuts only.
