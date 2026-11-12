---
created: "2026-11-08 06:32"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# Review deferrals filed as GitHub issues

A review finding outside a PR's scope is deferred into the gitignored `_bmad-output/implementation-artifacts/deferred-work.md` (see [deferred-work.md technical-debt ledger in gitignored _bmad-output](deferred-work-ledger-in-gitignored-output.md)), and at the end of a fix series those deferrals are filed as GitHub issues. Each item is re-verified against main, deduped against open issues, drafted and adversarially checked, then filed, and the ledger records "Filed on <date> as GitHub issues: #..." or a `## Filed as issues (<date>)` section. That ran from 2026-10-09 to 2026-10-13, and again on 2026-11-08 for the 9.0.0 series (#1022 to #1033) after the user answered "file them". Because the ledger is local, a deferral never filed is invisible to everyone else, and a goal like "address all issues" reads as finished while medium-severity defects stay untracked. Before reporting a fix series or an issues goal as done, list that series' unfiled deferrals and offer to file them.
