---
created: "2026-10-10 15:12"
session: "060dd6d3-2607-49df-93d3-74db880c67b5"
---

# PR merged before its fragment link commit landed

The maintainer can merge a PR minutes after it reads ready, before its `docs(changes): link this pull request's fragments to #N` commit, which adds `prs: [N]` to the change fragment, reaches the branch. On 2026-10-10 #707 merged at 11:30:40Z and its link commit landed at 11:31:54Z, so main got the fragment without `prs: [707]`. The fingerprint: `git ls-remote origin` shows the pushed SHA, but `gh pr view <n> --json headRefOid` keeps the old head, `gh api repos/{owner}/{repo}/commits/<sha>/check-runs` reports 0 runs, and `gh pr close <n>` fails with "can't be closed because it was already merged". When a pushed head never syncs, run `gh pr view <n> --json state,mergedAt` first. The repair is a one-line PR cut from `origin/main` (`git switch -c docs/link-707-fragment origin/main`, then `git cherry-pick -n` the link commit; merged as #709), which needs no fragment of its own because it touches only `changes/`. Opening the PR with `gh pr create --draft` and running `gh pr ready` once the link commit is green on that head avoids the race (a workaround, not a rule the maintainer stated).
