# Coverage Check: Branch Sections

Load this file only from the coverage-check.md sentence that names one of its sections, and follow that section alone: **States 2 to 4** from coverage-check.md §2 when the source is not local, and only its State 2 command from coverage-check.md §2b when `rebuild` is `provenance-fold`; **Scalar and Stack Branches** from coverage-check.md §2c on the scalar or stack branch; **Denominator Candidates** from coverage-check.md §4 when `denominator.clause` is `stratified-scope` or `multi-entry`. Load it once: when another sentence names one of its sections, read that section from the copy already loaded. A bare § in a section is coverage-check.md's. coverage-check.md's frontmatter bindings, its run files, its per-file results and its §2 **Exits** apply here unchanged. When the section is done, continue in coverage-check.md right after the sentence that loaded it.

## States 2 to 4

- **State 2** (`{forge_provenance_map}`, the provenance map init.md §2 bound): the union of its named exports and the `metadata.json` `exports[]` names, with `--fold`, `--keep` and `--fold-prefix` as the Source API Surface Definition's canonicalization says:

  ```bash
  uv run {coverageInputsScript} surface --provenance "{forge_provenance_map}" --metadata "{resolved_skill_package}/metadata.json" [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] [--fold] [--keep <variant>] [--fold-prefix <prefix>] [--monorepo] [--pattern-reference-intent] [--curated-subset] --output "{run_dir}/surface.json"
  ```

  Step 5's scoring script reads its `state2` counts, and the report its fold summary, `canonical.summary`.
- **State 3**: the `metadata.json` `exports[]` names: `surface --metadata "{resolved_skill_package}/metadata.json" [--monorepo] [--pattern-reference-intent] [--curated-subset] --output "{run_dir}/surface.json"`.
- **State 4**: the names read remotely by eye, as per-file results: `surface --per-file "{run_dir}/per-file-<n>.json" [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] --metadata "{resolved_skill_package}/metadata.json" [--monorepo] [--pattern-reference-intent] [--curated-subset] [--barrel <state>] --output "{run_dir}/surface.json"`.

## Scalar and Stack Branches

**A surplus is a signal, not a pass.** The scalar and stack branches count the numerator and denominator from independent sets, so `documented` can exceed `denominator`: it then reports `numeratorSurplus` above 0 and `coverageCapped: true`, holds `exportCoverage` at 100 and keeps the raw ratio in `coverageUncapped`, and §5's render states the surplus beside both counts. A large surplus is the deflated-denominator signature: check `guards.deflation`, whose `basis` names the set it measured the stored count against, before accepting the 100.

coverage-check.md §5b records this gap from the run files:

- **Missing count** (scalar or stack branch, `missingCount` above 0): one Medium `missing-export` gap for the count. When §2b's numerator check found the count inflated, its `absent[]` names replace this gap, one each: update-skill documents a named export, not a count.

## Denominator Candidates

```markdown
**Denominator Candidates** (stratified-scope audit trail):
- `stats.effective_denominator`: {statsEffectiveDenominator | absent}  {← chosen on the scalar branch}
- `scope.tier_a_include` union: {tierAIncludeUnion | absent}    {← chosen if the barrel branch's set}
- `scope.include` union: {scopeIncludeUnion | absent}           {← chosen if the barrel branch's set}
- exports-map subpath union: {subpathUnion | absent}        {← chosen if the barrel branch's set}
- root barrel: {rootBarrel | absent}                               {secondary candidate: root-barrel-vs-subpath-union audit}
```
