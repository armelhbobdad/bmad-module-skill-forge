---
# `{shardBodyHelper}`: the split below. If neither exists, it falls back to
# `skill-check split-body` or splits nothing, as the last bullet says.
shardBodyProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-shard-body.py'
  - '{project-root}/src/shared/scripts/skf-shard-body.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5b §7: Split an Oversized Body

verify-publish.md §7 loads this file when skill-check reports `body.max_lines` or `body.max_tokens`, then goes on to its next bullet. Every HALT below runs verify-publish.md's **Halt procedure**, and every warning follows verify-publish.md's **Warnings go to the run log** rule.

- If `body.max_lines` or `body.max_tokens` is reported, split the body selectively with `{shardBodyHelper}` (resolve it ← first existing path in `{shardBodyProbeOrder}`), **inside the verify-publish.md §0 guard**: from `{project-root}`, run `uv run {shardBodyHelper} "{skill_package}/SKILL.md" --budget 400 --word-budget 4500 --skip-manual`, with `--budget 500` in place of `--budget 400` when only `body.max_tokens` is reported. It moves the largest Tier 2 (`## Full`) sections to `references/`, each replaced by a `> See` pointer to a file it never overwrites, until the body is within that many lines and 4,500 words, the same headroom under skill-check's 5,000 that 400 lines leave under its 500, and keeps Tier 1 inline (inline passive context achieves 100% task accuracy vs 79% for on-demand retrieval). **Never move a section that holds a `[MANUAL]` block:** load-baseline.md §5 inventories SKILL.md only, so a block moved to `references/` would leave the next update's inventory; `--skip-manual` keeps the helper off every section a block reaches into. No Tier 1 content is trimmed, and `split-body` never runs after the helper. Add each WARN below to `warnings[]` as well. Act on its report:
  - **Exit 1 or 2, or no JSON:** HALT with status `blocked` (halt procedure: `phase: "write:body-split"`, `path: "{skill_package}/SKILL.md"`, `reason: "body split failed: {its stderr line}"`). On exit 2 that line ends `already written: {each references/*.md file it wrote before the failure, or none}`: name each of those files in the halt message.
  - **`tier1_preserved` false (it then wrote nothing) or `xref_ok` false:** HALT with status `blocked` (halt procedure: `phase: "write:body-split"`, `path: "{skill_package}/SKILL.md"`, `reason: "body split: tier1_missing {tier1_missing}; xref_ok {xref_ok}"`).
  - **`under_budget` false:** record `Spec compliance: WARN (body.max_lines: no Tier 2 section without a [MANUAL] block left to move)`.
  - **`under_word_budget` false:** record `Spec compliance: WARN (body.max_tokens: no Tier 2 section without a [MANUAL] block left to move)`.
  - **No `{shardBodyProbeOrder}` candidate resolves:** when `body.max_lines` is reported and SKILL.md holds no `[MANUAL]` block (write.md §1's verdict lists none), fall back to `npx skill-check split-body "{skill_package}" --write`, **inside the verify-publish.md §0 guard** (it can also touch frontmatter): it moves every section. When `body.max_lines` is reported and SKILL.md holds a `[MANUAL]` block, split nothing and record `Spec compliance: WARN (body.max_lines: skf-shard-body.py missing)`; when only `body.max_tokens` is reported, split nothing and record `Spec compliance: WARN (body.max_tokens: skf-shard-body.py missing)`.

  After a split (the helper's `sections_extracted` is not empty, or the fallback ran), re-read SKILL.md and each new `references/*.md` file into the in-context copy, as after `--fix`; re-run `npx skill-check check "{skill_package}" --format json --no-security-scan` and take the quality score and the remaining `diagnostics[]` from it; list in the Validation Summary's `Body split` row each section moved and the `references/` file it added; and verify anchors resolve.
