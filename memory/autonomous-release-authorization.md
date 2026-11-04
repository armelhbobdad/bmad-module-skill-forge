---
created: "2026-11-04 09:12"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# Standing authorization for autonomous end-to-end releases, both gates included

On 2026-11-04, during the 5.0.0 cut, the maintainer said "Once, green, merge and continue with the goal. You have now the authorization to autonously release a new package end to end." Until then the assistant left both human gates of `release.yaml` to the maintainer, as docs/_internal/RELEASING.md describes: gate 1, the `release` environment's required review (`gh api repos/armelhbobdad/bmad-module-skill-forge/actions/runs/<run>/pending_deployments` shows `current_user_can_approve: true`), and gate 2, an approval or admin-bypass merge of the bot PR `release/bot/v<version>-<run>-<n>`. With this authorization a release is cut without asking: dispatch `gh workflow run release.yaml --ref main -f version_bump=<bump>`, approve gate 1 through the `pending_deployments` API, merge the bot PR with `gh pr merge <n> --merge --admin` once its required checks are green (an approval alone stalls the run, see [Release bot PR never auto-merges](release-pr-auto-merge-deadlock.md)), then check npm `latest`, the tag, the GitHub Release and the docs deploy, and dispatch `install-smoke.yaml`. It narrows [Push, PR and merge each need the user's explicit go-ahead](push-pr-merge-need-explicit-go-ahead.md) for release cuts only. The dry run and the full suite still come first, and a red check or a failed step is reported, never forced past.
