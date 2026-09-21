---
created: "2026-08-06 11:10"
session: "5d852636-9449-426d-a518-ead3afd0a980"
source: claude-mem
source_table: observations
source_ids: [31898, 31961, 31988]
---

# Twin-file invariant on tools/validate-docs-links.js with bmad-module-ultracode-goal

`tools/validate-docs-links.js` is a twin of `../bmad-module-ultracode-goal/tools/validate-docs-links.js` (sibling repo checked out beside this one): only the narrative header comment differs, and from the first `^const ` line onward the two bodies must be byte-identical. Verify with `diff <(sed -n '/^const /,$p' tools/validate-docs-links.js) <(sed -n '/^const /,$p' ../bmad-module-ultracode-goal/tools/validate-docs-links.js)` — the output must be empty (it was at v2.1.0). `tools/build-docs.js` defers to the validator's `BUILD_INFRA_INPUTS` list as the single owner of the build-input set, so any body change ships as paired PRs in both repos (skill-forge #466/#467 were paired with ultracode-goal #93/#94). Nothing in the file header, CONTRIBUTING.md or docs/_internal names the sibling repo, so an edit made here alone silently breaks the invariant.
