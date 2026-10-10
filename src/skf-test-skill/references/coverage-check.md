---
nextStepFile: 'coherence-check.md'
outputFile: '{report_file}'
scoringRulesFile: 'references/scoring-rules.md'
sourceAccessProtocol: 'references/source-access-protocol.md'
coverageTiersFile: 'references/coverage-check-tiers.md'
validateInventoryScript: 'scripts/validate-inventory.py'
coverageInputsScript: 'scripts/load-coverage-inputs.py'
scoreSignaturesScript: 'scripts/score-signatures.py'
reconcileScript: 'scripts/reconcile-coverage.py'
coherenceScript: 'scripts/check-metadata-coherence.py'
numeratorVerifyScript: 'scripts/verify-declared-numerator.py'
stageHelperPayloadScript: 'scripts/stage-helper-payload.py'
outputFormatsFile: 'assets/output-section-formats.md'
ledgerFile: '{forge_version}/test-findings-{run_id}.json'
gapLedgerScript: 'scripts/gap-ledger.py'
# Each `<name>ProbeOrder` resolves `{<name>Helper}` to its first existing path:
# the installed SKF module first, the src/ dev checkout second.
verifyProvenanceCompletenessProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py'
  - '{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py'
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
detectWorkspacesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-workspaces.py'
  - '{project-root}/src/shared/scripts/skf-detect-workspaces.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Coverage Check

## STEP GOAL:

Compare the exports, functions, classes, types, and interfaces documented in SKILL.md against the actual source code API surface. Identify missing documentation, undocumented exports, and signature mismatches. Analysis depth scales with forge tier.

**Halt envelope.** Every HALT in this step names its `halt_reason` and phase and carries exit code 1. It releases the run lock first, whatever the release prints: from `{project-root}`, run `uv run {runLockHelper} release --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"` (SKILL.md Workflow Rules). In headless mode it then writes `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "skill_name": "{skill_name}", "report_path": "{report_file}"}`, adding `"path"` when the halt names one, to `{run_dir}/halt.json` and runs:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-test-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, as the run's last line, then stop. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

**Run files.** Every script below writes its result into the run folder `{run_dir}` that init.md §6b created, and the next one reads it from there by path. A subagent's response is saved there with the Write tool exactly as it came back, fence and all, and passed by path, so a quote or an apostrophe in it never meets a shell. Every count, name list and score a script computes is read from the file it wrote, never re-derived by hand or copied from one command into another. Each command runs from `{project-root}`; a `{...Script}` path resolves relative to the skill root.

### 0. Check for Docs-Only Mode

A skill is docs-only when every citation it writes is `[EXT:...]`, with no local source citation (`[AST:...]`, `[SRC:...]`, or a stack's `[from skill: ...]`). The citation census decides it:

```bash
uv run {coverageInputsScript} census --skill-dir "{resolved_skill_package}" --output "{run_dir}/census.json"
```

Bind `{docs_only_mode}` ← `docsOnly`. Exit 1 printed its error on stderr: HALT with it (`halt_reason: "helper-failed"`, phase `coverage-check:census`). §0b sets `{docs_only_mode}` too when source access reaches State 5.

**A docs-only run** measures documentation completeness as its Export Coverage, with `analysis_confidence` `docs-only`. It runs only §1, §1a and §1b, the docs-only guard of §2b, §2c's `docsOnly` branch, §4's Export Coverage line and its `Denominator: docs-only completeness` annotation, §5, §5b and §6. Step 5 passes `docsOnly: true` to the scoring script, which skips Signature Accuracy and Type Coverage at any tier.

"**Docs-only skill detected.** Coverage check evaluates documentation completeness rather than source code coverage."

A source-based skill continues with §0b.

### 0b. Load Source Access Protocol

Load `{sourceAccessProtocol}` and follow both sections: **Source API Surface Definition** (the clause that decides the coverage denominator, picked in §2b) and **Source Access Resolution** (the 5-state waterfall that decides how source files are read and sets `analysis_confidence`; State 5 makes the run docs-only).

**Workspace layout.** The Source API Surface Definition's monorepo tests read `{source_is_monorepo}`, which `{detectWorkspacesHelper}` decides. At State 1 (local source), resolve `{detectWorkspacesHelper}` ← first existing path in `{detectWorkspacesProbeOrder}` and run (`{stageHelperPayloadScript}` reads the source tree and the root manifests from disk and pipes them to the helper):

```bash
uv run {stageHelperPayloadScript} detect-workspaces --source-root "{source_path}" | uv run {detectWorkspacesHelper}
```

Bind `{source_is_monorepo}` ← `is_monorepo` and `{source_workspace_kind}` ← `manifest_kind`. At States 2 to 5, or when the helper does not resolve or the command exits non-zero, the layout is unknown: bind `{source_is_monorepo}` ← false. §5 records the layout.

### 1. Extract Documented Exports from SKILL.md

Delegate the reading of the skill under test to a subagent, given the path to SKILL.md and to its `references/` directory when one exists. The subagent reads SKILL.md, and every `references/*.md` file as well when SKILL.md's `## Full` headings are absent or stubs. For each export documented both in the SKILL.md body and in a reference file, it compares the two: parameters (name, type, order, optionality), the return type, and descriptions that contradict (brief against detailed is fine). It returns only this JSON, with no prose and no commentary:

```json
{
  "exports": [
    {"name": "functionName", "kind": "function", "params": "...", "return_type": "...", "description": "..."},
    {"name": "ClassName", "kind": "class", "methods": ["..."], "properties": ["..."], "description": "..."},
    {"name": "TypeName", "kind": "type", "fields": ["..."], "description": "..."},
    {"name": "useHook", "kind": "hook", "usage_signature": "...", "description": "..."}
  ],
  "references": ["references/api-reference.md"],
  "cross_check_mismatches": [
    {"export": "functionName", "skill_md_line": 42, "reference_file": "references/api-reference.md", "reference_line": 18, "issue": "SKILL.md shows (date: Date) => string, the reference (date: Date, format?: string) => string"}
  ]
}
```

Tell the subagent the contract the validator checks: each `kind` is one of `function`, `class`, `type`, `constant`, `hook`, `interface`, `method`, `struct`, `enum`, `trait`, `macro` or `adapter`; every entry carries the `description` the skill gives it (an empty string when it gives none); a function or method carries `params` (`""` or `[]` when it takes none) and `return_type` as the skill documents them, and leaves a key out when the skill documents nothing for it.

Save the subagent's response, as it came back, to `{run_dir}/inventory-response.txt` with the Write tool. The documented inventory is the one §1a validates: do not load SKILL.md or the reference files into the parent context. Without subagents, the parent reads the same files itself, builds the same JSON and saves it to the same file; §1a's checks still run on it.

#### 1a. Parent-Side Schema Validation + Spot-Check

Before anything consumes the inventory, `{validateInventoryScript}` checks it against the §1 contract (a wrapping fence stripped) and spot-checks sampled names against SKILL.md and the reference files the subagent listed. The look-up is the script's, never a grep: an export named `$state` or `a.b` is neither a shell variable nor a regex.

```bash
uv run {validateInventoryScript} --input "{run_dir}/inventory-response.txt" --skill-package "{resolved_skill_package}" --output "{run_dir}/inventory.json"
```

- `valid` true (exit 0): every later command reads `{run_dir}/inventory.json`.
- `valid` false (exit 2): re-dispatch the §1 subagent once, with the script's `violations[]` appended to its instructions (an absent name as a name the skill does not write), save the new response over the old one and run the command again. Invalid a second time: HALT (`halt_reason: "inventory-invalid"`, phase `coverage-check:inventory`): "coverage-check: the subagent inventory failed {schema validation | the ground-truth spot-check} twice: {the violations joined}."
- Exit 1 (no input, a file that cannot be read, or a package with no readable SKILL.md): correct the file and run it again.

### 1b. Cross-Check Split-Body Consistency

Only when the validated inventory's `references` is non-empty. The SKILL.md body is authoritative: each `cross_check_mismatches` entry is a High `split-body-mismatch` gap. §5b records it titled `Split-body mismatch: {export}`, with its `export` and its Source at the reference file's line (`{reference_file}:{reference_line}`), inside the skill package: the reference file is the one to update, and update-skill repairs it without reading the source.

### 2. Analyze Source Code (Tier-Dependent)

Identify the public API surface from the package entry points (see 0b), at the depth the tier allows. Whichever branch runs, `{coverageInputsScript} surface` writes it to `{run_dir}/surface.json`, which §2b, §2c, §4 and step 5 read. Names read by eye reach it as per-file results, `{"file": "<path>", "exports_found": [<each name>], "signature_mismatches": []}` for each file, saved to `{run_dir}/per-file-<n>.json` with the Write tool and given to `surface` with one `--per-file` each.

**Exits.** Every `{coverageInputsScript}` and `{scoreSignaturesScript}` command in §2 and §2b exits 0, or exits 1 with its error on stderr: HALT with it (`halt_reason: "helper-failed"`, phase `coverage-check:surface`). `surface` with a `--per-file`, and `score`, also exit 2 when a subagent response breaks the schema: re-dispatch that subagent once with its `violations[]` appended (or correct a result the main thread wrote), save the new response over the old one and run the command again; a second failure HALTs the same way.

**Quick Tier (no AST tools):** load `{coverageTiersFile}` and follow its **Quick Tier** section. Signatures cannot be verified at this tier: note them as "unverified" in the report.

**Forge Tier (ast-grep available):**

At State 1, run the recipe runner once over the source. Resolve `{extractPublicApiHelper}` ← first existing path in `{extractPublicApiProbeOrder}` and run it (leave `--brief` out when the skill has no brief; `--head-cap 0` keeps every match, so no export is cut and read as missing):

```bash
uv run {extractPublicApiHelper} --mode full --source-root "{source_path}" --brief "{forge_data_folder}/{skill_name}/skill-brief.yaml" --tier {detected_tier} --head-cap 0 --output "{run_dir}/extract-full.json"
```

Exit 2 is an input error (a brief the runner cannot read, say) or a failure the runner did not foresee, named in one line on stderr with no JSON: HALT with that line (`halt_reason: "helper-failed"`, phase `coverage-check:surface`). No Fallback Per-File Scan stands in for it: every flag here is fixed, so the error is a defect to surface.

Build the surface from it, with the metadata, the brief when the skill has one and, when init.md §2 bound one, the provenance map (the baselines of the §2b candidates and guards; they add no name):

```bash
uv run {coverageInputsScript} surface --extraction "{run_dir}/extract-full.json" --metadata "{resolved_skill_package}/metadata.json" [--provenance "{forge_provenance_map}"] [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] --output "{run_dir}/surface.json"
```

The surface holds the names the entry points export, less those defined in a file the brief scopes out (`excluded.outsideScope`); the recipes' internal matches are never part of it. A Python `__init__.py` nested in the folder of another package that exports a name is no barrel: its names (`excluded.nestedEntries`) leave only the `all` and `root` sets and the umbrella ratio, and `plan` still compares their signatures. When a `scope.include` glob matches no file (`guards.staleScope.fires`), the root exports defined in a file no glob covers and the brief does not exclude are back in it (`guards.staleScope.restored`). A stale `scope.tier_a_include` glob fires the guard too (`guards.staleScope.unmatchedTierAInclude`) and counts no name. List `excluded.outsideScope`, `excluded.nestedEntries` and the restored names in the report. Decide what to do from the JSON, not from the exit code:

- `extraction.fallback.needed` is true, or the runner printed no JSON on an exit other than 2: load `{coverageTiersFile}` and run its **Fallback Per-File Scan** in place of the rest of this tier.
- `extraction.status` is `incomplete` (exit 1): keep the surface, read by eye only the files `extraction.readByEye` names, save a per-file result for each, and run `surface` again with them.
- `extractionGaps[]` names exports no recipe found: they are on the surface, and their signature is read by eye at their `file` and `line`.

**Compare the signatures.** A script lists the comparisons; subagents judge them:

```bash
uv run {scoreSignaturesScript} plan --inventory "{run_dir}/inventory.json" --surface "{run_dir}/surface.json" --output "{run_dir}/signature-plan.json"
```

For each `files[]` entry, delegate one subagent with its checks. For each check it reads the full declaration at `{file}:{line}` (all of it: `signatureLine` is one physical line, and a multi-line signature cut there would read as a mismatch), compares it with the check's `documented` signature (params: name, type, order, optionality; and the return type), and returns only this JSON, with no prose and no markdown fences:

```json
{"file": "src/utils.ts", "signature_mismatches": [{"name": "formatDate", "line": 42, "source_sig": "(date: Date, format?: string) => string", "documented_sig": "(date: Date) => string", "issue": "missing optional parameter 'format'"}]}
```

Save each response to `{run_dir}/signatures-<n>.txt` with the Write tool. Without subagents, compare in the main thread and save the same JSON.

**Deep Tier (ast-grep + gh + QMD):** all Forge tier checks, plus: verify with the gh CLI that the source repository matches the documented version, cross-check type definitions against their source declarations, and trace re-exported symbols to their original source.

**States 2 to 4 (no local source):** the surface is what the skill recorded, so there is no signature to score:
- **State 2** (`{forge_provenance_map}`, the provenance map init.md §2 bound): the union of its named exports and the `metadata.json` `exports[]` names, with `--fold`, `--keep` and `--fold-prefix` as the Source API Surface Definition's canonicalization says:

  ```bash
  uv run {coverageInputsScript} surface --provenance "{forge_provenance_map}" --metadata "{resolved_skill_package}/metadata.json" [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] [--fold] [--keep <variant>] [--fold-prefix <prefix>] --output "{run_dir}/surface.json"
  ```

  Step 5's scoring script reads its `state2` counts, and the report records its fold summary, `canonical.summary`.
- **State 3**: the `metadata.json` `exports[]` names: `surface --metadata "{resolved_skill_package}/metadata.json" --output "{run_dir}/surface.json"`.
- **State 4**: the names read remotely by eye, as per-file results: `surface --per-file "{run_dir}/per-file-<n>.json" [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] --metadata "{resolved_skill_package}/metadata.json" --output "{run_dir}/surface.json"`.

### 2b. Resolve the Denominator and Guard Zero Exports

Load the metadata and provenance-map counts once, for §2c, §4b and the numerator check below (pass `--provenance` when init.md §2 bound `{forge_provenance_map}`):

```bash
uv run {coverageInputsScript} metadata --metadata "{resolved_skill_package}/metadata.json" [--provenance "{forge_provenance_map}"] --output "{run_dir}/coverage-inputs.json"
```

**Pick the denominator.** Which clause of the Source API Surface Definition (§0b) matches this skill is a judgment; the counts each clause names are in `surface.json` `candidates` and `guards`. The clause gives §2c its branch:

- **Standard barrel**, **multi-entry**, **specific-modules**, **pattern-reference**, State 2 or a priority-2/3 **stratified-scope** denominator: the barrel branch, over the `surface.json` set the clause names (`all`, `subpaths`, `tier_a_include` or `scope.include`). The scope sets need the brief's globs and names that carry their files (State 3's metadata names carry none), and `subpaths` and `root` an extraction. When the set is absent, the denominator is the `all` set, and the `Denominator:` line (§4) adds `({set} set absent: all set used)`.
- **Stratified-scope priority 1**: the scalar branch over `stats.effective_denominator` (`candidates.statsEffectiveDenominator`), unless `guards.deflation.fires`: then the barrel branch over the `scope.include` set (`all` when the brief has no `scope.include`).
- **A stack skill** (`metadata.json.skill_type == "stack"`): the stack branch, over `coverage-inputs.json` `stack.denominator`. Its own barrel is empty by design, and its `[from skill: …]` citations never make it docs-only. **If `stack.denominator` is 0**: HALT (`halt_reason: "indeterminate-surface"`, phase `coverage-check:denominator`) with `Error: stack composition surface empty: {skill_name} cites no contracts, libraries, or integration pairs, so Export Coverage is undefined. Verify the stack was compiled from at least one constituent skill.` Do not write the Coverage Analysis section; this is an indeterminate state, not a FAIL.
- **A docs-only skill**: the `docsOnly` branch, over the inventory.

**Numerator ground truth.** A declared count equal to the denominator (`stats.exports_documented == stats.effective_denominator`, the inflation signature) may be padded to a tautological 100%. Run the check on every source-based skill; without the signature (a stack and a reference app carry none) it reports `skipped`:

```bash
uv run {numeratorVerifyScript} --inputs "{run_dir}/coverage-inputs.json" --skill-dir "{resolved_skill_package}" --output "{run_dir}/numerator.json"
```

§2c's scalar branch takes its `verified` count as the numerator when `inflated` is true, and §4b records the gap. Exit 1 or 2: HALT with its message (`halt_reason: "helper-failed"`, phase `coverage-check:numerator`).

**If the chosen denominator is 0 AND `docs_only_mode == false` AND `metadata.json.skill_type != "stack"`:** HALT (`halt_reason: "indeterminate-surface"`, phase `coverage-check:denominator`) with:

```
Error: indeterminate API surface: 0 exports discovered in source for {skill_name}.

Export Coverage is undefined, and scoring would yield a vacuous PASS. Fix one of:
  - Set `scope.include` in the brief to point at the package's entry point(s)
  - Add `[EXT:]` citations if this is actually a docs-only skill
  - Verify the skill's source_path / source_ref resolve to the intended tree
```

Do not write the Coverage Analysis section or attach a score: this is an indeterminate state, not a FAIL. **If `docs_only_mode == true` and the validated inventory documents no item:** HALT the same way with "docs-only skill declares zero items: no API surface to test".

**Score the signatures** (Forge, Forge+ and Deep tier at State 1, once §2 compared them). Give `{scoreSignaturesScript}` the set the denominator counts as `--surface-set`: the set §2c's barrel branch reads, or for the scalar branch `tier_a_include` when `surface.json` has it, else `scope.include`, else `all`. Type Coverage then counts that set's types alone, so a type the clause leaves out (a stratified skill's deferred Tier B) lowers neither Export Coverage nor Type Coverage. Give it one `--results` per saved response (the fallback scan's `per-file-<n>.txt`, else the `signatures-<n>.txt`):

```bash
uv run {scoreSignaturesScript} score --inventory "{run_dir}/inventory.json" --surface "{run_dir}/surface.json" --surface-set <set> --results "{run_dir}/signatures-<n>.txt" --output "{run_dir}/signatures.json" --gaps-output "{run_dir}/signature-gaps.json"
```

It writes each mismatch of a compared name to `signature-gaps.json` as a Critical `signature-mismatch` gap titled `Signature mismatch: {name}`, with `export` `{name}`, its Source at `{file}:{line}` and both signatures in its Issue; §5b appends that file to the ledger. Its `warnings` (a mismatch for a name never compared, a category with nothing to compare) go in the Coverage Analysis section.

### 2c. Reconcile Documented vs Source Surface (Deterministic Intersection)

`{reconcileScript}` reconciles the §1 inventory with the source surface and writes `{run_dir}/coverage.json`, whose `exportCoverage` is the Export Coverage score step 5 hands to the scoring script. Run the branch §2b picked:

1. **Barrel**, with the name set §2b picked as `--surface-set`:

   ```bash
   uv run {reconcileScript} --denominator-source barrel --inventory "{run_dir}/inventory.json" --surface "{run_dir}/surface.json" --surface-set <set> --output "{run_dir}/coverage.json"
   ```

2. **Scalar**, over the `coverage-inputs.json` scalar; `--verified` makes §2b's `verified` count the numerator when the count was inflated:

   ```bash
   uv run {reconcileScript} --denominator-source scalar --coverage-inputs "{run_dir}/coverage-inputs.json" --inventory "{run_dir}/inventory.json" --skill-dir "{resolved_skill_package}" --verified "{run_dir}/numerator.json" --output "{run_dir}/coverage.json"
   ```

3. **Stack** (`metadata.json.skill_type == "stack"`):

   ```bash
   uv run {reconcileScript} --denominator-source stack --coverage-inputs "{run_dir}/coverage-inputs.json" --skill-dir "{resolved_skill_package}" --output "{run_dir}/coverage.json"
   ```

4. **Docs-only**: Export Coverage is the documentation completeness ratio, complete items over documented items, and `incomplete[]` lists each incomplete item with the fields it lacks:

   ```bash
   uv run {reconcileScript} --denominator-source docsOnly --inventory "{run_dir}/inventory.json" --output "{run_dir}/coverage.json"
   ```

Exit 2 printed an `INVALID_INPUT` envelope: correct the input it names and run it again. Exit 1: HALT with its stderr (`halt_reason: "helper-failed"`, phase `coverage-check:reconcile`).

**A surplus is a signal, not a pass.** The scalar and stack branches count the numerator and the denominator from independent sets, so `documented` can exceed `denominator`: the script then reports `numeratorSurplus` above 0 and `coverageCapped: true`, holds `exportCoverage` at 100 and keeps the raw ratio in `coverageUncapped`. State the surplus beside both counts in the Coverage Analysis section. On a skill with no `scope.tier_a_include` glob that matches a file, a large surplus is the deflated-denominator signature: check `guards.deflation` before accepting the 100.

**Classify what the script found.** §5b records each of these gaps from the run files:

- **Missing names** (barrel branch: `missing`): Medium `missing-export` gaps (Medium `missing-type` for a name `signatures.json` lists in `missingTypes`), each at the file `surface.json` records for it, so update-skill can re-extract the export from it. A missing export does not block: it lowers Export Coverage.
- **Missing count** (scalar or stack branch, `missingCount` above 0): one Medium `missing-export` gap for the count. When §2b's numerator ground-truth check found the count inflated, its `absent[]` names replace this gap, one each: update-skill documents a named export, not a count.
- **Stale names** (barrel branch: `stale`): each is a documented name the enumerated source surface lacks. Where ast-grep read the source at the pinned commit (Forge, Forge+ or Deep tier, `analysis_confidence` `full`, `workspaceDrift` not `overridden` in the `{outputFile}` frontmatter) and init.md §2 bound `{forge_provenance_map}`, check the lines the skill cites for them: resolve `{verifyProvenanceCompletenessHelper}` ← first existing path in `{verifyProvenanceCompletenessProbeOrder}` and run once:

  ```bash
  uv run {verifyProvenanceCompletenessHelper} classify-stale --names "{run_dir}/coverage.json" --provenance "{forge_provenance_map}" --source-root "{source_path}" --inventory "{run_dir}/inventory.json" -o "{run_dir}/stale.json"
  ```

  A name it marks `fabricated: true` (every map entry of the name cites a missing file or one that does not define it) is a Critical `fabricated-signature` gap at its `source`. A name with a `defined_at` (the source still declares it there, an import never counting, a module so named counting unless the name's inventory kind rules it out), or whose `declared_in` lists several files of which the skill's `[AST:]`/`[SRC:]` citations on lines naming it cite exactly one, is a documented extra: an Info `observation` gap at that declaration, when `surface.json` has an `extraction` and its `excluded.outsideScope` does not list the name (a brief scoped its file out). Any other stale name (no `defined_at` and no single cited declaring file, one scoped out, no `extraction`, a dotted name, the conditions above not met, a helper that does not resolve or exits non-zero) is a Medium `stale-documentation` gap.

### 4. Category Scores and the Denominator Record

Each category score is read from its script's file, the file step 5 hands to the scoring script:

- **Export Coverage:** `coverage.json` `exportCoverage`
- **Signature Accuracy:** `signatures.json` `signatureAccuracy` (Forge, Forge+ and Deep tier at State 1; "N/A" otherwise)
- **Type Coverage:** `signatures.json` `typeCoverage`, over the types of the set §2b scored; "N/A" where Signature Accuracy is

Record the denominator source in the Coverage Analysis section with the annotation the matching clause of `{sourceAccessProtocol}` specifies: `Denominator: {barrel | stratified (…) | multi-entry (…) | specific-modules (…) | pattern-reference (…) | stack composition (…) | pattern-surface (…) | docs-only completeness}`, and the `canonical.summary` line when `surface.json` has a fold. When stratified-scope or multi-entry resolution picked the denominator, append this block right after the `Denominator:` line, with every count from `surface.json` `candidates` (`absent` for a null one):

```markdown
**Denominator Candidates** (stratified-scope audit trail):
- `stats.effective_denominator`: {statsEffectiveDenominator | absent}  {← chosen if priority (1) applied}
- `scope.tier_a_include` union: {tierAIncludeUnion | absent}    {← chosen if priority (2) applied}
- `scope.include` union: {scopeIncludeUnion | absent}           {← chosen if priority (3) applied}
- exports-map subpath union: {subpathUnion | absent}        {← chosen if the multi-entry clause applied}
- root barrel: {rootBarrel | absent}                               {secondary candidate: root-barrel-vs-subpath-union audit}
```

The guards raise coverage gaps too, which §5b records from `surface.json`: `guards.deflation.fires` is a Medium `metadata-drift` gap, `guards.inflation.fires` a Medium `denominator-inflation` gap and `guards.staleScope.fires` a Medium `brief-scope-stale` gap at the brief.

### 4b. Metadata Export-Count Coherence Cross-Check

`{coherenceScript}` compares the `coverage-inputs.json` counts and owns every skip (a stack, a reference app, a cluster with fewer than two counts, drift within its threshold):

```bash
uv run {coherenceScript} --inputs "{run_dir}/coverage-inputs.json" > "{run_dir}/metadata-coherence.json"
```

A non-zero exit leaves the script's error, or nothing, in that file: delete it, so §5b skips its call and records no count finding, and note the error in the Coverage Analysis section. §5b records each `findings[]` entry: a Medium entry as a Medium `metadata-drift` gap and an Info entry as an Info `multi-denominator` gap. They describe data quality and change no denominator. Record the denominator of a stack (`Denominator: stack composition ({N} cited contracts)` or `({N} libraries + integration pairs)`, from `stack.basis`) and of a reference app (`Denominator: pattern-surface ({pattern_surfaces_documented})`).

**The numerator ground truth §2b ran.** `numerator.json` `inflated: true` (`verified < declared`) is a High `numerator-inflation` gap listing its `absent[]` names, which §5b records; on the scalar branch those names also replace §2c's missing-count gap. `inflated: false` or `skipped: true` is no finding.

### 4c. Provenance Line Check

Check that the provenance map records each export at the line that defines it (the `def` or declaration line itself, not a decorator or blank line above it), so update-skill can move a wrong line. Run this section only when `analysis_confidence` is `full`, `{forge_version}/provenance-map.json` exists, and the `{outputFile}` frontmatter's `workspaceDrift` is not `overridden` (init.md §5b: the drifted tree is not the pinned commit). Otherwise skip to section 5.

Resolve `{verifyProvenanceCompletenessHelper}` ← first existing path in `{verifyProvenanceCompletenessProbeOrder}`. If neither path exists, skip to section 5: the check is advisory. Otherwise run:

```bash
uv run {verifyProvenanceCompletenessHelper} verify \
    --metadata {resolved_skill_package}/metadata.json \
    --provenance {forge_version}/provenance-map.json \
    --source-root {source_path} \
    -o "{run_dir}/provenance-verify.json"
```

Rely on the file, not the exit code (exit 1 means findings); on exit 2 the helper writes no file: skip to section 5. §5b records each `stale[]` item whose `reason` is `line-not-definition`: a Low `provenance-line` gap when its `definition_lines` holds a line, else an Info `provenance-unverified` gap (the rules may not cover its shape: the export is unverified, not gone). Its Source is exactly the `file:line` the map records, the citation update-skill's rule R5 reads.

This section reports none of the helper's other findings, and neither gap blocks the gate.

### 5. Write the Coverage Analysis Section

Write the **Coverage Analysis** section in place of the template's `## Coverage Analysis` heading and the placeholder comment under it, in `{outputFile}`. The counts come from `{run_dir}/coverage.json` and `{run_dir}/signatures.json`:

```markdown
## Coverage Analysis

**Tier:** {forge_tier}
**Source Access:** {analysis_confidence} (full | provenance-map | metadata-only | remote-only | docs-only)
**Source Path:** {source_path}
**Workspace Layout:** {source_workspace_kind | single package | unknown (no local source, or the §0b helper failed)}
**Files Analyzed:** {count}
**Denominator:** {the §4 annotation}

### Export Coverage

| Export | Type | Documented | Signature | Source Location | Status |
|--------|------|-----------|-----------|-----------------|--------|
| {name} | {kind} | yes/no | yes/no/unverified | {file}:{line} | PASS/FAIL/WARN |

### Coverage Summary

- **Exports Found:** {`denominator`; docs-only: the documented items}
- **Documented:** {`documented`} ({`exportCoverage`}%)
- **Missing Documentation:** {`missingCount`; docs-only: the incomplete items, each with the fields it lacks}
- **Signature Mismatches:** {the length of `signatures.json` `mismatches`}
- **Stale Documentation:** {`staleCount`}, documented extras included (§2c)
- **Scoring Warnings:** each entry of `signatures.json` `warnings`; omit this row when there is none
- **Numerator Surplus:** {`numeratorSurplus`}, uncapped coverage {`coverageUncapped`}%; only when `coverageCapped: true` (then `Missing Documentation: 0` is a floored residual)

### Category Scores

| Category | Score |
|----------|-------|
| Export Coverage | {N}% |
| Signature Accuracy | {N}% or N/A |
| Type Coverage | {N}% or N/A |
```

### 5b. Record the Coverage Gaps

Record every gap this step found in the gap ledger `{ledgerFile}`: the hard gate (step 4c) decides from it, and the report step renders the Gap Report from it. `{gapLedgerScript}` writes the record of each gap a script found from that script's file: §2b's signature mismatches, §2c's missing names, missing count and stale names, §4's guard gaps, §4b's count findings and numerator gap, and §4c's provenance line gaps, each with the severity and category of its row in the Gap Severity table of `{scoringRulesFile}` and a fixed title, Source, `export` and Remediation. Run each command whose `--input` file this run wrote, leaving out a bracketed flag whose file does not exist: a run file this run did not write, or `--provenance` when init.md §2 bound no `{forge_provenance_map}`:

```bash
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --input "{run_dir}/signature-gaps.json"
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from coverage --input "{run_dir}/coverage.json" [--surface "{run_dir}/surface.json"] [--signatures "{run_dir}/signatures.json"] [--numerator "{run_dir}/numerator.json"] [--stale "{run_dir}/stale.json"] [--provenance "{forge_provenance_map}"] --skill-dir "{resolved_skill_package}" --metadata "{resolved_skill_package}/metadata.json"
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from guards --input "{run_dir}/surface.json" --metadata "{resolved_skill_package}/metadata.json"
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from numerator --input "{run_dir}/numerator.json" --metadata "{resolved_skill_package}/metadata.json"
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from metadata-coherence --input "{run_dir}/metadata-coherence.json" --metadata "{resolved_skill_package}/metadata.json"
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from provenance-line --input "{run_dir}/provenance-verify.json"
```

Then write the records no script wrote, §1b's split-body mismatches, in the Ledger Record Format of `{outputFormatsFile}`, each naming its export in `export` and in its title: the ledger tells two gaps apart by their title, Source and `export`, and update-skill takes the export's name from `export`. Write them as one JSON array on the lines between the two markers, exactly as they are: the quoted marker hands them to the script unchanged, quotes, apostrophes and `$` included. Run the command even when the array is empty (`[]`): the hard gate refuses to decide until every stage before it has recorded, with gaps or without.

```bash
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check <<'SKF_GAPS'
<the records, one JSON array>
SKF_GAPS
```

Rely on the JSON of each command:

- Exit 0: the records are in the ledger. `appended` names the id each new record received, and `duplicates` the ones a rerun of this step had already recorded.
- Exit 2 (`INVALID_RECORD` or `INVALID_INPUT`): nothing was written. Correct each record `errors[]` names (its `index` counts from 0), or the file or flag the `error` names, and run the command again.
- Exit 1: HALT with the script's `error` (`halt_reason: "helper-failed"`, phase `coverage-check:ledger`).

### 6. Report Coverage Results

Report the coverage result to the user: the {forge_tier}-tier analysis of {file_count} source files, the documented ratios for exports / signatures / types (signatures and types are N/A for Quick tier), and the issue count. Full details are in the Coverage Analysis section.

Append `'coverage-check'` to `stepsCompleted` in the `{outputFile}` frontmatter, then load and execute {nextStepFile}.
