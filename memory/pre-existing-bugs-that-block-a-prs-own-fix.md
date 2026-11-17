---
created: "2026-11-17 16:59"
session: "ebc4edf5-1536-4f23-a3e9-90b0b13c44e9"
---

# Pre-existing bugs that block a PR's own fix

Review triage sends a pre-existing defect to `defer` (the `deferred-work.md` ledger, then a GitHub issue at the end of a series), but not one that keeps the pull request's own fix from ever taking effect: fix that one in the same PR. On 2026-11-17, PR #1240 for #1237 fixed the health check's [R]/[C] reaction for a `HOST/OWNER/REPO` `health_check_repo`, and the first review found that `gh search issues --repo` takes only OWNER/REPO and searches gh's default host (`Invalid search query "... repo:ghe.example.com/acme/skills ..."`), so a GitHub Enterprise Server run failed at the dedup search before the reaction could run; #1237's own note had wrongly said `gh search issues` takes the host. The assistant deferred it as an old bug not caused by the change, because fixing it changed the documented headless allow rules, while the PR body still said "Fixes #1237"; the user answered "fix fix fix". The same branch then moved both searches to `gh issue list --repo {healthCheckRepo} --search`, with a `breaking` fragment for the allow-rule migration, a type the user confirmed when asked. When a deferral would leave the fixed path unreachable, or let a closing keyword mark an issue done while its scenario still fails, fix the blocker in the PR and ask only about the decisions it raises, such as a fragment's type. Related: [Review deferrals filed as GitHub issues](review-deferrals-filed-as-github-issues.md).
