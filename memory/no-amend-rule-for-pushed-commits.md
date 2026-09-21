---
created: "2026-04-21 14:47"
session: "0bcaebd1-df5f-4b64-b72d-1795416d0356"
source: claude-mem
source_table: observations
source_ids: [6852]
---

# No-amend rule for pushed commits

Commits already pushed to a branch are never amended, squashed away or force-pushed, even when they are debugging noise or net-zero; they are reverted so the commit chain stays intact as the audit trail of the debugging path (the "no amend / no force-push" rule). On `feat/release-workflow`, `f449c67` (a superseded `--force` fix attempt) and `e470501`/`7208ff4` (a net-zero pair) were deliberately left in place and disclosed as commit noise in the PR body rather than rewritten away. Branch protection (`docs/_internal/RELEASING.md` § Branch Protection on `main`, `non_fast_forward`) only blocks force-push on `main`, so this rule is what governs feature branches.
