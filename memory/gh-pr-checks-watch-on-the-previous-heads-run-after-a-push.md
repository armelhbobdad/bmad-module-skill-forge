---
created: "2026-10-10 07:46"
session: "060dd6d3-2607-49df-93d3-74db880c67b5"
---

# gh pr checks --watch on the previous head's run after a push

Started right after `git push` to an open PR, `gh pr checks <n> --watch` can watch the previous head's run, because the new head's run has not registered yet (or never will, once the PR has merged), so its exit status says nothing about the pushed commit. On 2026-10-10 on PR #705, a watch chained after the push exited 1 at once on the old failed run while the new run was still pending; a second watch, started once the new run showed pending, went green. On #707 a watch exited 0 on run 38044347923 for the old head ca723eec although 6f66eb4d had just been pushed. Before reading a watch as green or red, confirm the run belongs to the pushed SHA with `gh run view <id> --json headSha,conclusion` or `gh pr view <n> --json headRefOid`, or poll `gh api repos/{owner}/{repo}/commits/<sha>/check-runs` for that exact SHA. This differs from the empty check list on a brand-new PR (`memory/ci-check-runs-lag-new-pr`): here the list is full, but for the wrong commit.
