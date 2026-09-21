---
created: "2026-03-18 08:23"
session: "1055aa88-193b-4061-9b3a-069e8ce17271"
source: claude-mem
source_table: both
source_ids: [1725, 1816, 1803]
---

# Deep review for breaking changes before each batched push or PR

Owner rule for pushes and PRs: "before we push every 13 commits, please run a last deep review for any general breaking changes, missing impact, etc..." — before a batch of accumulated commits is pushed or a PR is opened, run one deep review over the whole batch (`git log origin/main..HEAD`, walk the diff) hunting breaking changes, impacts missed in sibling workflows/steps, and regressions of fixes made earlier in the same batch, verifying those earlier fixes with grep sweeps rather than from memory ("we should make sure it adhere with the previous issues already fixed"). The cadence was set when work landed in 12–15 commit batches on a since-deleted `dev` branch; work now flows main ← feature-branch PRs, but the rule is layout-independent. It exists because that pass caught real cross-step bugs that `npm run quality` — which `CONTRIBUTING.md § The Quality Gate` presents as the only pre-push gate — did not.
