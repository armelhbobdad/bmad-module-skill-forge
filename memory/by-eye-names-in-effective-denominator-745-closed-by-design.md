---
created: "2026-10-13 10:38"
session: "060dd6d3-2607-49df-93d3-74db880c67b5"
---

# By-eye names in effective_denominator (#745 closed by design)

Create Skill counts the names of entry points it reads by eye, in files no recipe reads (`files_without_recipes_list`), in `stats.effective_denominator`, each name once. The rule is the paragraph opening with section 5's `init` in `src/skf-create-skill/references/extract.md` (steps 2 to 4 of `{entryPointsByHandData}` with `--extraction`), and Update Skill's recount from #741 follows it. Issue #745 proposed leaving those names out so the stored count matched the recipe runner's own view, and on 2026-10-13 the maintainer chose "Close as by design (Recommended)", so it was closed as not planned. The built fix made Test Skill score worse: its numerator still counts a documented by-eye name, so a fixture skill documenting `Widget` and `alpha` but not `Beta` scored 100.0 instead of 66.67, with the gap unreported. Its fallback per-file scan and Quick-tier re-derivation also read those files, so the lower stored count raised a false Medium `metadata-drift` deflation gap. Do not re-file or re-implement the exclusion, and point a health-check issue that asks for it to #745's closing comment, unless Test Skill's numerator and re-derivations change in the same commit (memory/effective-denominator-producer-consumer-coupling).
