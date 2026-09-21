---
created: "2026-04-25 00:19"
session: "07e394fc-8689-4ad9-95e8-90a9f20b5dcd"
source: claude-mem
source_table: session_summaries
source_ids: [7525, 7526, 7528, 7529, 7530]
---

# Release bot PR never auto-merges: perpetually pending code_quality rule

The `main` ruleset (id 13855503) carries a `code_quality` rule (`severity: errors`) but no Code Scanning workflow ever reports against it, so the bot PR that `release.yaml` opens ends up `reviewDecision: APPROVED`, all required checks green, yet `mergeStateStatus: BLOCKED` — the head commit's combined status reads `pending` with an empty `statuses` array and no incomplete check-runs. `gh pr merge --auto --merge --delete-branch` (the `Auto-merge bot PR` step) therefore never fires and the run stalls at `Wait for merge completion`; first hit on PR #241 (v1.1.0). The way through is an admin-bypass merge — the PR merge button or `gh pr merge <n> --admin --merge` (squash for ordinary PRs) — which `release.yaml`'s `Wait for PR approval or admin-bypass merge` step accepts; docs/_internal/RELEASING.md calls this 'the observed pattern' but does not say why. The rule is still in the live ruleset and the v2.0.1/v2.0.2/v2.1.0 release PRs (#450, #452, #469) all merged with `autoMergeRequest: null`, so expect the same stall until `code_quality` is removed or satisfied.
