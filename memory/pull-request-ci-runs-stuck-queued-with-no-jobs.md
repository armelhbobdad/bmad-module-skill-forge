---
created: "2026-11-12 00:34"
session: "72e9f28d-d28a-41b5-917c-b01a8cd78569"
---

# Pull request CI runs stuck queued with no jobs

On 2026-11-12 the `pull_request` Quality & Validation runs of PR #1100, mergeable and not conflicting, sat `queued` with 0 jobs for over 25 minutes while GitHub status showed Actions operational. `gh run cancel` answered `Cannot cancel a workflow run that is completed` and `gh pr close` then `gh pr reopen` only queued another empty run, but `gh workflow run quality.yaml --ref <branch>` scheduled all 10 jobs within 30 s. Their check runs on the head SHA satisfied the 10 required checks, though `gh pr checks <n>` kept printing `no checks reported on the '<branch>' branch`, so watch `gh api repos/{owner}/{repo}/commits/<sha>/check-runs`, where the newest run of each required name counts. Merge through the API with the head SHA pinned: `gh api -X PUT repos/{owner}/{repo}/pulls/<n>/merge -f merge_method=merge -f sha=<sha>`. A dispatch run skips the `Change fragments this pull request needs` step, which runs only when `github.event_name == 'pull_request'`, so run `npm run changes:pr` locally first. When a mergeable PR's runs stay `queued` with no jobs well past the few minutes check runs normally take, dispatch `quality.yaml` on its branch instead of waiting.
