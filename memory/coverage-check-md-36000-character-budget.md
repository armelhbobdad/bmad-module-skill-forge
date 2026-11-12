---
created: "2026-11-03 13:43"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# coverage-check.md 36,000-character budget

`COVERAGE_CHAR_BUDGET = 36_000` in `test/test-skf-test-skill-provenance-paths.py` caps `src/skf-test-skill/references/coverage-check.md` (a stand-in for about 9,000 cl100k tokens, #600), counted as Python `len(text)`, not `wc -c` bytes, and the file sits just under it (35,986 characters on 2026-11-12). Nearly every change that adds a rule there must make room, and branches that each pass alone overflow once stacked or rebased together: the pre-commit hook failed with `AssertionError: 36684` / `assert 36684 < 36000`, and 25920f87 and 6e9bcda1 had to trim after landing. When several lanes edit the file, split the headroom between them and run `test_coverage_check_stays_under_its_budget_and_loads_each_carved_branch` on the combined tree before shipping. Trims made only to fit have silently changed what the model is told (on 2026-11-03 the Deep Tier check lost "original" and "source", so a re-export trace could stop at the first barrel) and no test caught it, so check every trim against the original wording. Rarely taken branches can move to `coverage-check-branches.md` (`{coverageBranchesFile}`), but `CARVED_TO_BRANCHES` in the test pins the moved blocks byte for byte, so editing carved text means updating that copy too.
