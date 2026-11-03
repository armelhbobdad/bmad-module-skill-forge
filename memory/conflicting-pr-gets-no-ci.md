---
created: "2026-11-03 22:54"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# A conflicting PR gets no CI, so a stacked chain's merge wait hangs

On 2026-11-03 two stacked chains (each branch cut from the previous PR's head, merged in order by `ship-after.sh` and `ship-merge.sh`) shipped #848 to #859 while #851, a docs PR from another session, merged into `main` mid-chain. The chain branches never contained #851: the PRs that did not touch its lines merged cleanly, but #859 edited the same lines of `docs/verifying-a-skill.md` and became `mergeable: CONFLICTING`, `mergeStateStatus: DIRTY`. GitHub runs no `pull_request` workflow on a conflicting PR, so `gh pr checks 859` and `gh run list --branch fix/scalar-branch-named-surface` stayed empty, and the merge script, which waits for every check to pass on the head SHA, waited with no error. When a check list is still empty after the few minutes CI normally takes to register, run `gh pr view <n> --json mergeable,mergeStateStatus` first. The fix was to rebase the PR onto `origin/main`, keep main's text and re-apply the PR's point, run the full `npm test` on the rebased head, push with `--force-with-lease`, and restart the merge wait with the new head SHA (a wait started on the old SHA polls for it forever). Since a chain is tested only against its own base, run the full suite on `main` once the chain has merged.
