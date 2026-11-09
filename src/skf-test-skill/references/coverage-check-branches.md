# Coverage Check: Branch Sections

Load this file only from the coverage-check.md sentence that names one of its sections, and follow that section alone: **Inventory Failures** from coverage-check.md §1a when the inventory check fails; **States 2 to 4** from coverage-check.md §2 when the source is not local, and only its State 2 command from coverage-check.md §2b when `rebuild` is `provenance-fold`; **Scalar and Stack Branches** from coverage-check.md §2c on the scalar or stack branch; **Denominator Candidates** from coverage-check.md §4 when `denominator.clause` is `stratified-scope` or `multi-entry`; **Metadata Count Cross-Check** from coverage-check.md §4b; **Docs-Only Run** from coverage-check.md §0 when the run is docs-only; **Split-Body Sources** from coverage-check.md §5b when §1b found a split-body mismatch. Load it once: when another sentence names one of its sections, read that section from the copy already loaded. A bare § in a section is coverage-check.md's. coverage-check.md's frontmatter bindings, its run files, its per-file results and its §2 **Exits** apply here unchanged. When the section is done, continue in coverage-check.md right after the sentence that loaded it.

## Inventory Failures

- **`valid` false (exit 2):** delete the response `{validateInventoryScript}` refused, so a stale one is never validated twice:

  ```bash
  rm -f "{run_dir}/inventory-response.txt"
  ```

  Re-dispatch the §1 subagent once, with the script's `violations[]` appended to its instructions (an absent name as a name the skill does not write, a floor name as one it must keep): it writes its new response to that file, or returns it for you to save there, as §1 says. Run the §1a command again.
- **Exit 1** (no input, a file that cannot be read, or a package with no readable SKILL.md): correct the file and run it again. An error that names `--floor` (the floor file missing or malformed): run §1's `floor` command again, whose exit 1 halts the run `helper-failed` as §1 says, then the §1a command.

## States 2 to 4

- **State 2** (`{forge_provenance_map}`, the provenance map init.md §2 bound): the union of its named exports and the `metadata.json` `exports[]` names, with `--fold`, `--keep` and `--fold-prefix` as the Source API Surface Definition's canonicalization says:

  ```bash
  uv run {coverageInputsScript} surface --provenance "{forge_provenance_map}" --metadata "{resolved_skill_package}/metadata.json" [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] [--fold] [--keep <variant>] [--fold-prefix <prefix>] [--monorepo] [--pattern-reference-intent] [--curated-subset] --output "{run_dir}/surface.json"
  ```

  Step 5's scoring script reads its `state2` counts, and the report its fold summary, `canonical.summary`.
- **State 3**: the `metadata.json` `exports[]` names: `surface --metadata "{resolved_skill_package}/metadata.json" [--monorepo] [--pattern-reference-intent] [--curated-subset] --output "{run_dir}/surface.json"`.
- **State 4**: the names read remotely by eye, as per-file results: `surface --per-file "{run_dir}/per-file-<n>.json" [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] --metadata "{resolved_skill_package}/metadata.json" [--monorepo] [--pattern-reference-intent] [--curated-subset] [--barrel <state>] --output "{run_dir}/surface.json"`.

## Scalar and Stack Branches

Run the command of the branch §2b picked; §2c's exits apply to it:

- **Scalar**, over the `coverage-inputs.json` scalar and §2b's set (`denominator.surfaceSet`); `--verified` makes §2b's `verified` count the numerator when the count was inflated and the branch counts no set:

  ```bash
  uv run {reconcileScript} --denominator-source scalar --coverage-inputs "{run_dir}/coverage-inputs.json" --inventory "{run_dir}/inventory.json" --surface "{run_dir}/surface.json" --surface-set <set> --skill-dir "{resolved_skill_package}" --verified "{run_dir}/numerator.json" --output "{run_dir}/coverage.json"
  ```

- **Stack** (`metadata.json.skill_type == "stack"`):

  ```bash
  uv run {reconcileScript} --denominator-source stack --coverage-inputs "{run_dir}/coverage-inputs.json" --skill-dir "{resolved_skill_package}" --output "{run_dir}/coverage.json"
  ```

**The scalar branch counts §2b's set** only when `surface.json` `denominator.setCounted` is true: a scope set (not `all`) whose every name sits at the file that defines it (a complete runner extraction, the fallback scan, or quick output that traces each name), read whole. Then `numeratorSource` is `surface`: `documented` counts the documented names the set holds (`documentedNames`), so a documented name the set lacks never offsets an undocumented one; `missing` lists the set's undocumented names; §5's render draws the per-export table; and the denominator stays the stored count, so when the set's size (`surfaceSetSize`) differs from it, `warnings` names both. Otherwise (`all`, a set read by eye or from an incomplete extraction, or an empty set, which warns) the branch looks each documented name up in the skill, `--verified` applies, and `missing` lists no name. On any surface read from the source (`guards.deflation.applicable` true), `stale` lists the documented names the whole surface lacks (the set, the `all` set and each name on a `surface.json` `exports` record, a nested entry's included: the barrel branch finds `stale` against the same surface), with `staleApplicable` true, so §2c's Stale names bullet applies: a documented name outside the set that the source still exports is neither counted nor stale. §5's render lists each `warnings` entry.

**A surplus is a signal, not a pass.** Where the numerator and denominator count independent sets (the stack branch, and the scalar branch when it counts no set), `documented` can exceed `denominator`, as it can when a counted set holds more names than the stored count: `coverage.json` then reports `numeratorSurplus` above 0 and `coverageCapped: true`, holds `exportCoverage` at 100 and keeps the raw ratio in `coverageUncapped`, and §5's render states the surplus beside both counts. A large surplus is the deflated-denominator signature: check `guards.deflation`, whose `basis` names the set it measured the stored count against, before accepting the 100.

coverage-check.md §5b records this gap from the run files:

- **Missing count** (scalar or stack branch, `missingCount` above 0): one Medium `missing-export` gap for the count. A scalar result that counts its set records its `missing` names as §2c's Missing names bullet says instead, plus one gap for the rest when `missingCount` exceeds them. When §2b's numerator check found the count inflated and the scalar branch counted no set, its `absent[]` names replace this gap, one each: update-skill documents a named export, not a count.

## Denominator Candidates

```markdown
**Denominator Candidates** (stratified-scope audit trail):
- `stats.effective_denominator`: {statsEffectiveDenominator | absent}  {← chosen on the scalar branch}
- `scope.tier_a_include` union: {tierAIncludeUnion | absent}    {← chosen if the barrel branch's set}
- `scope.include` union: {scopeIncludeUnion | absent}           {← chosen if the barrel branch's set}
- exports-map subpath union: {subpathUnion | absent}        {← chosen if the barrel branch's set}
- root barrel: {rootBarrel | absent}                               {secondary candidate: root-barrel-vs-subpath-union audit}
```

## Metadata Count Cross-Check

`{coherenceScript}` compares the `coverage-inputs.json` counts and owns every skip (a stack, a reference app, a cluster with fewer than two counts, drift within its threshold):

```bash
uv run {coherenceScript} --inputs "{run_dir}/coverage-inputs.json" > "{run_dir}/metadata-coherence.json"
```

A non-zero exit leaves the script's error, or nothing, in that file: delete it, so §5b skips its call and records no count finding, and note the error in the Coverage Analysis section. §5b records each `findings[]` entry: a Medium entry as a Medium `metadata-drift` gap and an Info entry as an Info `multi-denominator` gap. They describe data quality and change no denominator. Record the denominator of a stack (`Denominator: stack composition ({N} cited contracts)` or `({N} libraries + integration pairs)`, from `stack.basis`) and of a reference app (`Denominator: pattern-surface ({pattern_surfaces_documented})`).

## Docs-Only Run

**A docs-only run** measures documentation completeness as its Export Coverage, with `analysis_confidence` `docs-only`. It runs only §1, §1a and §1b, the docs-only guard of §2b, §2c's `docsOnly` branch, §4's `Denominator: docs-only completeness` annotation, §5, §5b and §6. Step 5 passes `docsOnly: true` to the scoring script, which skips Signature Accuracy and Type Coverage at any tier.

"**Docs-only skill detected.** Coverage check evaluates documentation completeness rather than source code coverage."

§2c's `docsOnly` branch: Export Coverage is the documentation completeness ratio, complete over documented items, and `incomplete[]` lists each incomplete item with the fields it lacks:

```bash
uv run {reconcileScript} --denominator-source docsOnly --inventory "{run_dir}/inventory.json" --output "{run_dir}/coverage.json"
```

## Split-Body Sources

The Source is `{reference_file}:{reference_line}`, of two references the one that sorts last, unless the pinned source settles it for the other side. At State 1 and the Forge tier or above, with `workspaceDrift` not `overridden`, load `{signatureRulesFile}` and set the two forms its `issue` gives against the export's declaration at the `file` and `line` `surface.json` gives, by its rules, when that one declaration decides (no overload set, no second declaring file, and an `otherDeclarations` list, not `null`, with no entry of the export's name; `null` means no runner extraction looked for one, as after the fallback per-file scan): when `{reference_file}`'s form agrees and the other side's does not, the Source is the other side, `SKILL.md:{skill_md_line}` or `{other_file}:{other_line}`. A pair that gives an `owner` is a `method`'s (inventory-contract.md): its declaration is the member of the method's bare name that the owner's body declares, read from the `file` and `line` of the owner's `surface.json` record, or, for an owner that binds the name to a function declared elsewhere (a keyword of the `types.SimpleNamespace(...)` call that builds it, a class attribute assigned a function), the declaration that binding names, read in the owner's file or through its import, and it decides when the owner's name has one declaration by the test above and the owner declares or binds the member once, with no overload set. A record of the bare name never stands in for the member, so with no record of the owner or no such member, or with no `owner` on a pair whose `export` the inventory lists only as a `method`, nothing decides. Its remediation names the file to edit and the file and line whose form it takes, citing the declaration's `file:line`; when both forms agree with it, it says so and names what differs; when neither does, or nothing decides, it says no source settled it and names `{reference_file}` to edit, taking the other side's form (`{other_file}`'s, for two references). Under the State, tier and `workspaceDrift` conditions above, when nothing decides because the export's name has more than one declaration (a second declaring file, or an `otherDeclarations` entry of its name), on a pair that gives no `owner` and whose `export` the inventory does not list only as a `method`, set each form against each declaration of the name, its `surface.json` records and its `otherDeclarations` entries, read at their `file` and `line`, or found by its name in its `file` when its `line` is `null` (a per-file record): when each form agrees with a different one, the remediation names no form to take. For each side it gives the form's file and line and the declaration that form agrees with, and asks update-skill to add that declaration's citation, `[SRC:{file}:L{line}]`, or `[SRC:{file}]` for one with no `line`, which names every declaration in its file, on the form's line or, in a fenced block, on a comment line just above it, and to name the declaration's module or owner beside the form, so a later run's reader and §2's `bound` keep the two apart. Its Source stays `{reference_file}:{reference_line}` and its **Contradicted Side** `not settled`; every other pair keeps the remediation above.
